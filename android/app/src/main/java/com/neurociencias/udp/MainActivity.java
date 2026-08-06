package com.neurociencias.udp;

import android.database.ContentObserver;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private FrameLayout blackoutOverlay;
    private TextView watermarkText;
    private Handler screenshotHandler;
    private ContentObserver screenshotObserver;
    private boolean isBlackoutActive = false;
    private boolean isInExam = false; // Se activa cuando el estudiante está rindiendo

    // ⚠️ CAMBIA ESTA URL POR LA QUE TE DÉ RAILWAY O RENDER
    private static final String APP_URL = "https://neurociencias-app-production.up.railway.app";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // ==========================================
        // 1. FLAG_SECURE - BLOQUEO PRINCIPAL
        // ==========================================
        // Esta es la defensa principal de Android:
        // Cuando se intenta tomar un screenshot, Android muestra
        // automáticamente una imagen NEGRA en lugar del contenido.
        // Funciona en TODOS los dispositivos Android estándar.
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,
                WindowManager.LayoutParams.FLAG_SECURE);

        // ==========================================
        // 2. INICIALIZAR VISTAS
        // ==========================================
        webView = findViewById(R.id.webView);
        blackoutOverlay = findViewById(R.id.blackoutOverlay);
        watermarkText = findViewById(R.id.watermarkText);

        // ==========================================
        // 3. DETECCIÓN DE SCREENSHOT VIA CONTENT OBSERVER
        //    Monitorea la carpeta de screenshots (Android 10+)
        // ==========================================
        screenshotHandler = new Handler(Looper.getMainLooper());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            screenshotObserver = new ContentObserver(screenshotHandler) {
                @Override
                public void onChange(boolean selfChange, Uri uri) {
                    super.onChange(selfChange, uri);
                    // Se detectó un cambio en la galería - posible screenshot
                    if (isInExam) {
                        onScreenshotDetected();
                    }
                }
            };
            getContentResolver().registerContentObserver(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    true,
                    screenshotObserver
            );
        }

        // ==========================================
        // 4. CONFIGURAR WEBVIEW
        // ==========================================
        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webSettings.setAllowFileAccess(false);
        webSettings.setAllowContentAccess(false);
        webSettings.setBuiltInZoomControls(false);
        webSettings.setDisplayZoomControls(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Detectar si estamos en la página del examen
                if (url.contains("/estudiante/rendir/")) {
                    isInExam = true;
                    showWatermark();
                } else {
                    isInExam = false;
                    hideWatermark();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient());

        // Interfaz JavaScript para comunicación desde la web
        webView.addJavascriptInterface(new WebAppInterface(), "Android");

        webView.loadUrl(APP_URL);
    }

    // ==========================================
    // 5. MARCA DE AGUA PERMANENTE
    //    Se muestra MIENTRAS el estudiante rinde el examen
    //    Así, cualquier screenshot tendrá esta advertencia visible
    // ==========================================
    private void showWatermark() {
        runOnUiThread(() -> {
            watermarkText.setVisibility(View.VISIBLE);
            watermarkText.bringToFront();
        });
    }

    private void hideWatermark() {
        runOnUiThread(() -> {
            watermarkText.setVisibility(View.GONE);
        });
    }

    // ==========================================
    // 6. BLOQUEAR BOTÓN DE VOLVER
    // ==========================================
    @Override
    public void onBackPressed() {
        // Bloqueado completamente durante el examen
        if (isInExam) {
            Toast.makeText(this, "No puedes salir durante el examen", Toast.LENGTH_SHORT).show();
        } else {
            // Fuera del examen, permitir salir
            super.onBackPressed();
        }
    }

    // ==========================================
    // 7. MANEJADOR DE SCREENSHOT DETECTADO
    // ==========================================
    private void onScreenshotDetected() {
        if (isBlackoutActive) return;
        isBlackoutActive = true;

        // 1. Mostrar pantalla negra INMEDIATAMENTE
        showBlackout();

        // 2. Notificar al WebView para finalizar la prueba
        webView.evaluateJavascript(
            "javascript:(function() { " +
            "  if (typeof finalizarPrueba === 'function') { " +
            "    finalizarPrueba('Finalizado por captura de pantalla'); " +
            "  }" +
            "})()", null);

        // 3. Mantener pantalla negra por 8 segundos
        new Handler().postDelayed(() -> {
            isBlackoutActive = false;
            blackoutOverlay.setVisibility(View.GONE);
            isInExam = false;
            hideWatermark();
        }, 8000);
    }

    // ==========================================
    // 8. PANTALLA NEGRA
    // ==========================================
    private void showBlackout() {
        runOnUiThread(() -> {
            blackoutOverlay.setVisibility(View.VISIBLE);
            blackoutOverlay.setBackgroundColor(Color.BLACK);
            blackoutOverlay.bringToFront();
        });
    }

    // ==========================================
    // 9. INTERFAZ JAVASCRIPT
    // ==========================================
    public class WebAppInterface {
        @JavascriptInterface
        public boolean isScreenshotBlocked() {
            return true;
        }

        @JavascriptInterface
        public void showToast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface
        public void examStarted() {
            isInExam = true;
            showWatermark();
        }

        @JavascriptInterface
        public void examFinished() {
            isInExam = false;
            hideWatermark();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Re-aplicar FLAG_SECURE al reanudar
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,
                WindowManager.LayoutParams.FLAG_SECURE);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (screenshotObserver != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                getContentResolver().unregisterContentObserver(screenshotObserver);
            } catch (Exception e) {
                // Ignorar
            }
        }
    }
}