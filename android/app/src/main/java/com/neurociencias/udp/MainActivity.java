package com.neurociencias.udp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.webkit.WebViewCompat;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private FrameLayout blackoutOverlay;
    private static final String APP_URL = "https://neurociencias-udp.up.railway.app"; // CAMBIAR POR TU URL

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // ==========================================
        // 1. BLOQUEO DE SCREENSHOTS (FLAG_SECURE)
        // ==========================================
        // Esta es la línea MÁS IMPORTANTE: FLAG_SECURE evita que se pueda
        // tomar screenshot o grabar la pantalla en Android.
        // Cuando el usuario intenta tomar un screenshot, Android muestra
        // una pantalla en negro automáticamente.
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,
                WindowManager.LayoutParams.FLAG_SECURE);

        // ==========================================
        // 2. DETECCIÓN DE SCREENSHOT (Android 14+)
        // ==========================================
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // En Android 14+ podemos detectar screenshots
            registerReceiver(screenshotReceiver,
                    new IntentFilter("android.intent.action.SCREENSHOT"),
                    RECEIVER_EXPORTED);
        }

        // ==========================================
        // 3. CONFIGURAR WEBVIEW
        // ==========================================
        webView = findViewById(R.id.webView);
        blackoutOverlay = findViewById(R.id.blackoutOverlay);

        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webSettings.setAllowFileAccess(false);
        webSettings.setAllowContentAccess(false);

        // Deshabilitar zoom
        webSettings.setBuiltInZoomControls(false);
        webSettings.setDisplayZoomControls(false);

        // Forzar que los links se abran dentro del WebView
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                // Permitir navegación interna
                return false;
            }
        });

        // Habilitar Chrome Client para alerts y confirmaciones
        webView.setWebChromeClient(new WebChromeClient());

        // Agregar interfaz JavaScript para comunicación desde la web
        webView.addJavascriptInterface(new WebAppInterface(), "Android");

        // Cargar la URL de la aplicación
        webView.loadUrl(APP_URL);
    }

    // ==========================================
    // 4. BLOQUEAR BOTÓN DE VOLVER
    // ==========================================
    @Override
    public void onBackPressed() {
        // No hacer nada - bloquea el botón de volver
        // Si quieres permitir volver en ciertas páginas, puedes usar:
        // if (webView.canGoBack()) {
        //     webView.goBack();
        // } else {
        //     super.onBackPressed();
        // }
    }

    // ==========================================
    // 5. DETECCIÓN DE SCREENSHOT (Android 14+)
    // ==========================================
    private final BroadcastReceiver screenshotReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            // Se detectó un screenshot - mostrar pantalla negra
            showBlackout();
            
            // Notificar al WebView
            webView.evaluateJavascript(
                "javascript:(function() { " +
                "  if (typeof finalizarPrueba === 'function') { " +
                "    finalizarPrueba('Finalizado por captura de pantalla'); " +
                "  }" +
                "})()", null);
        }
    };

    // ==========================================
    // 6. PANTALLA NEGRA DE PROTECCIÓN
    // ==========================================
    private void showBlackout() {
        blackoutOverlay.setVisibility(View.VISIBLE);
        blackoutOverlay.setBackgroundColor(Color.BLACK);
        
        new Handler().postDelayed(() -> {
            blackoutOverlay.setVisibility(View.GONE);
        }, 5000); // 5 segundos de pantalla negra
    }

    // ==========================================
    // 7. INTERFAZ JAVASCRIPT PARA LA WEB
    // ==========================================
    public class WebAppInterface {
        @JavascriptInterface
        public boolean isScreenshotBlocked() {
            return true; // Siempre está bloqueado
        }

        @JavascriptInterface
        public void showToast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            try {
                unregisterReceiver(screenshotReceiver);
            } catch (Exception e) {
                // Ignorar si no está registrado
            }
        }
    }
}