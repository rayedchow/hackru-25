import SwiftUI
import ReplayKit
import UIKit

struct ContentView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "brain").imageScale(.large).foregroundStyle(.tint)
            Text("Synapse")

            BroadcastLauncher(preferredExtension: "com.rayedchow.nourishment.nourishmentBroadcast")
                .frame(width: 220, height: 44)
        }
        .padding()
    }
}

struct BroadcastLauncher: UIViewRepresentable {
    let preferredExtension: String

    func makeUIView(context: Context) -> UIView {
        let container = UIView()

        // Hidden system picker
        let picker = RPSystemBroadcastPickerView(frame: .zero)
        picker.preferredExtension = preferredExtension
        picker.isHidden = true
        container.addSubview(picker)
        context.coordinator.picker = picker

        // Visible button you control
        let btn = UIButton(type: .system)
        btn.setTitle("Start Streaming Reels", for: .normal)
        btn.addTarget(context.coordinator, action: #selector(Coordinator.tapPicker), for: .touchUpInside)
        btn.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(btn)

        NSLayoutConstraint.activate([
            btn.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            btn.centerYAnchor.constraint(equalTo: container.centerYAnchor),
        ])
        return container
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject {
        weak var picker: RPSystemBroadcastPickerView?
        @objc func tapPicker() {
            guard let picker = picker else { return }
            // Find the internal UIButton and trigger it
            for v in picker.subviews {
                if let b = v as? UIButton {
                    b.sendActions(for: .touchUpInside)
                    return
                }
            }
        }
    }
}

#Preview { ContentView() }
