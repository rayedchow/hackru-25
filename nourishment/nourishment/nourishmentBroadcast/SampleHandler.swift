import ReplayKit
import AVFoundation
import CoreImage
import UIKit

final class SampleHandler: RPBroadcastSampleHandler {

    // MARK: Config
    private let uploadURL = URL(string: "https://d73559d3afca.ngrok-free.app/upload")!
    private let chunkSeconds: Double = 2.0

    // MARK: State
    private var ciContext = CIContext(options: nil)
    private var latestJPEGData = Data()              // most recent frame as JPEG
    private let stateQueue = DispatchQueue(label: "rp.state") // serialize access

    private var chunkTimer: DispatchSourceTimer?

    override func broadcastStarted(withSetupInfo setupInfo: [String : NSObject]?) {
        print("📡 Broadcast started, timer set to \(chunkSeconds)s")
        let t = DispatchSource.makeTimerSource(queue: .global(qos: .utility))
        t.schedule(deadline: .now() + chunkSeconds, repeating: chunkSeconds)
        t.setEventHandler { [weak self] in
            guard let self = self else { return }
            print("⏰ Timer fired - flushing video")
            self.flushVideoFrame()   // send latest frame (once per 5s)
        }
        t.resume()
        chunkTimer = t
    }

    override func broadcastFinished() {
        flushVideoFrame()
        chunkTimer?.cancel()
        chunkTimer = nil
    }

    override func processSampleBuffer(_ sb: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        switch sampleBufferType {
        case .video:
            cacheLatestJPEG(sb)
        case .audioApp, .audioMic:
            // Audio handling removed
            break
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
        guard !toSend.isEmpty else {
            print("⚠️ No video frame to send")
            return
        }
        print("📹 Sending video frame (\(toSend.count) bytes)")
        let b64 = toSend.base64EncodedString()
        postJSON(["type":"video","payload":b64])
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
