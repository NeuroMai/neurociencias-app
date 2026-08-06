import SwiftUI
import WebKit

// MARK: - Vista Principal
struct ContentView: View {
    // URL del backend - CAMBIAR POR LA URL DE RAILWAY/RENDER
    private let appURL = "https://neurociencias-udp.up.railway.app"
    
    @StateObject private var viewModel = WebViewModel()
    @State private var showWatermark = false
    @State private var isBlackout = false
    
    var body: some View {
        ZStack {
            // Capa 1: WebView
            WebViewContainer(
                url: appURL,
                viewModel: viewModel,
                showWatermark: $showWatermark,
                isBlackout: $isBlackout
            )
            .edgesIgnoringSafeArea(.all)
            
            // Capa 2: Marca de agua (visible durante el examen)
            if showWatermark {
                WatermarkView()
                    .allowsHitTesting(false) // No bloquea la interacción
            }
            
            // Capa 3: Pantalla negra (al detectar screenshot)
            if isBlackout {
                Color.black
                    .edgesIgnoringSafeArea(.all)
                    .transition(.opacity)
            }
        }
        .onAppear {
            // Detectar screenshots en iOS
            setupScreenshotDetection()
        }
    }
    
    // MARK: - Detección de Screenshots (iOS 14+)
    private func setupScreenshotDetection() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.userDidTakeScreenshotNotification,
            object: nil,
            queue: .main
        ) { _ in
            if showWatermark {
                // Solo durante el examen
                withAnimation(.easeInOut(duration: 0.3)) {
                    isBlackout = true
                }
                
                // Notificar al WebView para finalizar la prueba
                viewModel.evaluateJavaScript("""
                    if (typeof finalizarPrueba === 'function') {
                        finalizarPrueba('Finalizado por captura de pantalla');
                    }
                """)
                
                // Mantener pantalla negra por 8 segundos
                DispatchQueue.main.asyncAfter(deadline: .now() + 8) {
                    withAnimation {
                        isBlackout = false
                        showWatermark = false
                    }
                }
            }
        }
    }
}

// MARK: - WebView Container usando WKWebView
struct WebViewContainer: UIViewRepresentable {
    let url: String
    @ObservedObject var viewModel: WebViewModel
    @Binding var showWatermark: Bool
    @Binding var isBlackout: Bool
    
    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }
    
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let userContentController = WKUserContentController()
        
        // Agregar interfaz JavaScript
        userContentController.add(context.coordinator, name: "iOSApp")
        
        config.userContentController = userContentController
        
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.scrollView.isScrollEnabled = true
        webView.allowsBackForwardNavigationGestures = false // Bloquear gestos de navegación
        
        // Deshabilitar zoom
        webView.scrollView.minimumZoomScale = 1.0
        webView.scrollView.maximumZoomScale = 1.0
        
        if let url = URL(string: url) {
            webView.load(URLRequest(url: url))
        }
        
        // Guardar referencia
        viewModel.webView = webView
        
        return webView
    }
    
    func updateUIView(_ uiView: WKWebView, context: Context) {}
    
    // MARK: - Coordinator
    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        var parent: WebViewContainer
        
        init(_ parent: WebViewContainer) {
            self.parent = parent
        }
        
        // Detectar cambios de página
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            if let url = webView.url?.absoluteString {
                // Detectar si estamos en la página del examen
                if url.contains("/estudiante/rendir/") {
                    parent.showWatermark = true
                } else {
                    parent.showWatermark = false
                }
            }
        }
        
        // Bloquear navegación externa (todo dentro del WebView)
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Permitir navegación interna
            decisionHandler(.allow)
        }
        
        // Recibir mensajes desde JavaScript
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "iOSApp" {
                if let body = message.body as? String {
                    if body == "examStarted" {
                        parent.showWatermark = true
                    } else if body == "examFinished" {
                        parent.showWatermark = false
                    } else if body == "screenshotDetected" {
                        // Ya se manejó desde iOS
                    }
                }
            }
        }
    }
}

// MARK: - ViewModel para comunicación con WebView
class WebViewModel: ObservableObject {
    weak var webView: WKWebView?
    
    func evaluateJavaScript(_ script: String) {
        webView?.evaluateJavaScript(script, completionHandler: nil)
    }
}

// MARK: - Marca de Agua
struct WatermarkView: View {
    var body: some View {
        GeometryReader { geometry in
            Text("⚠️ CAPTURA DE PANTALLA\nNO PERMITIDA ⚠️\nEvaluación Protegida\nNeurociencias UDP")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(.red.opacity(0.4))
                .multilineTextAlignment(.center)
                .lineSpacing(10)
                .rotationEffect(.degrees(-25))
                .frame(width: geometry.size.width * 1.5, height: geometry.size.height)
                .position(x: geometry.size.width / 2, y: geometry.size.height / 2)
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Preview
struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}