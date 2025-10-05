import ReplayKit
import AVFoundation
import CoreImage
import UIKit

final class SampleHandler: RPBroadcastSampleHandler {

    // MARK: Config
    private let uploadURL = URL(string: "https://c008ec00190b.ngrok-free.app/upload")!
    private let chunkSeconds: Double = 2.0
    private let audioSampleRate: Double = 48_000
    private let audioChannels: Int = 2

    // MARK: State
    private var ciContext = CIContext(options: nil)
    private var latestJPEGData = Data()              // most recent frame as JPEG
    private let stateQueue = DispatchQueue(label: "rp.state") // serialize access

    private var audioBuffer = [Float]()              // float32 interleaved
    private var chunkTimer: DispatchSourceTimer?

    override func broadcastStarted(withSetupInfo setupInfo: [String : NSObject]?) {
        let t = DispatchSource.makeTimerSource(queue: .global(qos: .utility))
        t.schedule(deadline: .now() + chunkSeconds, repeating: chunkSeconds)
        t.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.flushAudioChunk()   // send 5s audio
            self.flushVideoFrame()   // send latest frame (once per 5s)
        }
        t.resume()
        chunkTimer = t
    }

    override func broadcastFinished() {
        flushAudioChunk()
        flushVideoFrame()
        chunkTimer?.cancel()
        chunkTimer = nil
    }

    override func processSampleBuffer(_ sb: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        switch sampleBufferType {
        case .video:
            cacheLatestJPEG(sb)
        case .audioApp, .audioMic:
            collectAudio(sb)
        @unknown default:
            break
        }
    }

    // MARK: Video: keep only the latest frame as JPEG (fast & tiny)
    private func cacheLatestJPEG(_ sb: CMSampleBuffer) {
        guard let pb = CMSampleBufferGetImageBuffer(sb) else { return }
        let ci = CIImage(cvPixelBuffer: pb)
        guard let cg = ciContext.createCGImage(ci, from: ci.extent) else { return }
        let ui = UIImage(cgImage: cg)
        guard let jpeg = ui.jpegData(compressionQuality: 0.6) else { return }
        stateQueue.async { self.latestJPEGData = jpeg }
    }

    private func flushVideoFrame() {
        var toSend = Data()
        stateQueue.sync { toSend = self.latestJPEGData }
        guard !toSend.isEmpty else { return }
        let b64 = toSend.base64EncodedString()
        postJSON(["type":"video","payload":b64])
    }

    // MARK: Audio
    private func collectAudio(_ sb: CMSampleBuffer) {
        guard let block = CMSampleBufferGetDataBuffer(sb) else { return }

        var len = 0
        var dataPtr: UnsafeMutablePointer<Int8>?
        CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &len, dataPointerOut: &dataPtr)
        guard let p = dataPtr, len > 0 else { return }

        let count = len / MemoryLayout<Float>.size
        p.withMemoryRebound(to: Float.self, capacity: count) { src in
            stateQueue.async {
                self.audioBuffer.append(contentsOf: UnsafeBufferPointer(start: src, count: count))
            }
        }
    }

    private func flushAudioChunk() {
        var samples: [Float] = []
        stateQueue.sync {
            guard !audioBuffer.isEmpty else { return }
            samples = audioBuffer
            audioBuffer.removeAll(keepingCapacity: true)
        }
        guard !samples.isEmpty else { return }

        let wav = writeWAVFloat32(samples: samples,
                                  sampleRate: UInt32(audioSampleRate),
                                  channels: UInt16(audioChannels))
        let b64 = wav.base64EncodedString()
        postJSON(["type":"audio","payload":b64])
    }

    // Tiny WAV (float32 interleaved)
    private func writeWAVFloat32(samples: [Float], sampleRate: UInt32, channels: UInt16) -> Data {
        let byteRate = sampleRate * UInt32(channels) * 4
        let blockAlign = UInt16(channels * 4)
        let dataSize = UInt32(samples.count * 4)

        var d = Data()
        func a(_ s: String) { d.append(s.data(using: .ascii)!) }
        func u32(_ v: UInt32) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 4)) }
        func u16(_ v: UInt16) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 2)) }

        a("RIFF"); u32(36 + dataSize); a("WAVE")
        a("fmt "); u32(16); u16(3); u16(channels); u32(sampleRate)
        u32(byteRate); u16(blockAlign); u16(32)
        a("data"); u32(dataSize)
        var copy = samples
        d.append(Data(bytes: &copy, count: Int(dataSize)))
        return d
    }

    // MARK: Minimal POST
    private func postJSON(_ obj: [String: Any]) {
        guard let body = try? JSONSerialization.data(withJSONObject: obj) else { return }
        var req = URLRequest(url: uploadURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        URLSession(configuration: .ephemeral).dataTask(with: req).resume()
    }
}
