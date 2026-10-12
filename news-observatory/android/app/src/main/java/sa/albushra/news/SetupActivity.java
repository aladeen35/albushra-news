package sa.albushra.news;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

/** First launch (or "change server"): ask for the newsroom's address. */
public class SetupActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_setup);
        EditText input = findViewById(R.id.url);
        TextView message = findViewById(R.id.message);
        Button save = findViewById(R.id.save);
        input.setText(Server.get(this));
        save.setOnClickListener(v -> {
            String url = Server.normalise(input.getText().toString());
            if (url.isEmpty()) {
                message.setText(R.string.setup_invalid);
                return;
            }
            Server.set(this, url);
            Intent open = new Intent(this, MainActivity.class);
            open.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(open);
            finish();
        });
    }
}
