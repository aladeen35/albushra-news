package sa.albushra.news;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.core.content.FileProvider;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.io.File;
import java.io.FileOutputStream;

/**
 * The newsroom in a WebView. Pages from the configured server stay inside the
 * app; every other link (a story's original page, a source's site) opens in
 * the phone's browser. Pull down to refresh; Back walks the page history.
 */
public class MainActivity extends Activity {
    private WebView web;
    private View error;
    private SwipeRefreshLayout refresh;
    private String server;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        server = Server.get(this);
        if (server.isEmpty()) {
            startActivity(new Intent(this, SetupActivity.class));
            finish();
            return;
        }
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        error = findViewById(R.id.error);
        refresh = findViewById(R.id.refresh);
        refresh.setColorSchemeColors(getColor(R.color.accent), getColor(R.color.brand));
        refresh.setOnRefreshListener(() -> web.reload());
        findViewById(R.id.retry).setOnClickListener(v -> {
            error.setVisibility(View.GONE);
            web.reload();
        });
        findViewById(R.id.change_server).setOnClickListener(v -> openSetup());

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);           // settings, saved stories, admin session
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setUserAgentString(s.getUserAgentString() + " AlBushraApp/" + BuildConfig.VERSION_NAME);

        // Lets the web app's settings page offer "change server" inside the app.
        web.addJavascriptInterface(new Bridge(), "AlBushraApp");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (Server.sameHost(server, uri)) return false;
                openOutside(uri);
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                error.setVisibility(View.GONE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                refresh.setRefreshing(false);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError err) {
                if (request.isForMainFrame()) {
                    refresh.setRefreshing(false);
                    error.setVisibility(View.VISIBLE);
                }
            }
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(server + "/");
    }

    private void openOutside(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException ignored) {
            // No app can open it; stay where we are.
        }
    }

    private void openSetup() {
        startActivity(new Intent(this, SetupActivity.class));
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    private final class Bridge {
        @JavascriptInterface
        public void openServerSettings() {
            runOnUiThread(MainActivity.this::openSetup);
        }

        @JavascriptInterface
        public String version() {
            return BuildConfig.VERSION_NAME;
        }

        /**
         * A story card from the page (a PNG data URL) handed to the system
         * share sheet as an image file, with its caption, so WhatsApp and the
         * rest receive the picture itself. The WebView has no navigator.share.
         */
        @JavascriptInterface
        public boolean shareImage(String dataUrl, String text) {
            try {
                String data = dataUrl.substring(dataUrl.indexOf(',') + 1);
                byte[] bytes = Base64.decode(data, Base64.DEFAULT);
                File dir = new File(getCacheDir(), "share");
                if (!dir.isDirectory() && !dir.mkdirs()) return false;
                File[] old = dir.listFiles();
                if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
                    f.delete();
                File file = new File(dir, "albushra-news-" + System.currentTimeMillis() + ".png");
                try (FileOutputStream out = new FileOutputStream(file)) {
                    out.write(bytes);
                }
                Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".fileprovider", file);
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("image/png");
                send.putExtra(Intent.EXTRA_STREAM, uri);
                if (text != null && !text.isEmpty()) send.putExtra(Intent.EXTRA_TEXT, text);
                send.setClipData(ClipData.newRawUri(file.getName(), uri));
                send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                runOnUiThread(() -> startActivity(Intent.createChooser(send, null)));
                return true;
            } catch (Exception e) {
                return false;
            }
        }
    }
}
