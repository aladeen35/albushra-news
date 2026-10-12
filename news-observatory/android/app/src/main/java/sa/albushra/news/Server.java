package sa.albushra.news;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;

/** Where the newsroom lives: the address chosen in the app, else the one built in. */
final class Server {
    private static final String PREFS = "albushra";
    private static final String KEY = "server_url";

    private Server() {}

    static String get(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String saved = prefs.getString(KEY, "");
        if (saved != null && !saved.isEmpty()) return saved;
        return normalise(BuildConfig.SERVER_URL);
    }

    static void set(Context context, String url) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, url).apply();
    }

    /** "news.example.com" -> "https://news.example.com"; anything not https is refused (""). */
    static String normalise(String raw) {
        if (raw == null) return "";
        String url = raw.trim();
        if (url.isEmpty()) return "";
        if (!url.contains("://")) url = "https://" + url;
        Uri uri = Uri.parse(url);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getHost().isEmpty()) {
            return "";
        }
        while (url.endsWith("/")) url = url.substring(0, url.length() - 1);
        return url;
    }

    static boolean sameHost(String serverUrl, Uri target) {
        Uri server = Uri.parse(serverUrl);
        return target.getHost() != null && target.getHost().equalsIgnoreCase(server.getHost());
    }
}
