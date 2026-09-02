import ReplayKit
import AVFoundation
import CoreImage
import UIKit

final class SampleHandler: RPBroadcastSampleHandler {

    // MARK: Config
    private let chunkSeconds: Double = 2.0
    private let requestTimeoutSeconds: Double = 10.0

    private var uploadURL: URL? {
        guard
            let configured = Bundle.main.object(forInfoDictionaryKey: "SynapseUploadURL") as? String,
            !configured.isEmpty,
            !configured.contains("$("),
            let url = URL(string: configured),
            url.scheme == "https"
        else {
            return nil
        }
        return url
    }

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
        stateQueue.sync { latestJPEGData.removeAll(keepingCapacity: false) }
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
        guard let uploadURL else {
            print("🔒 SynapseUploadURL is not configured; frame stays on this device")
            return
        }
        var toSend = Data()
        stateQueue.sync {
            toSend = self.latestJPEGData
            self.latestJPEGData.removeAll(keepingCapacity: false)
        }
        guard !toSend.isEmpty else {
            print("⚠️ No video frame to send")
            return
        }
        print("📹 Sending video frame (\(toSend.count) bytes)")
        let b64 = toSend.base64EncodedString()
        postJSON(["type":"video","payload":b64,"source":"ios-replaykit"], to: uploadURL)
    }

    // MARK: Minimal POST
    private func postJSON(_ obj: [String: Any], to uploadURL: URL) {
        guard let body = try? JSONSerialization.data(withJSONObject: obj) else { return }
        var req = URLRequest(url: uploadURL)
        req.httpMethod = "POST"
        req.timeoutInterval = requestTimeoutSeconds
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = requestTimeoutSeconds
        configuration.timeoutIntervalForResource = requestTimeoutSeconds
        URLSession(configuration: configuration).dataTask(with: req).resume()
    }
}
