package dev.drtino.arch;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.InputStreamReader;

/** Sin UI: pide root, verifica la chroot y cambia a Linux nativo (Phosh en la pantalla). */
public class LaunchActivity extends Activity {
    private static final String NATIVE = "/data/local/arch-tools/native";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        new Thread(this::launch).start();
    }

    private void launch() {
        String check = su("test -x " + NATIVE + " && echo ok");
        if (check == null) {
            toast("Sin root. Corré df.root y dale root a Arch en KernelSU.");
            return;
        }
        if (!check.contains("ok")) {
            toast("No encuentro " + NATIVE);
            return;
        }
        toast("Arrancando Linux…");
        // setsid + nohup: el script sigue aunque esta app termine.
        su("nohup setsid " + NATIVE + " start </dev/null >/dev/null 2>&1 &");
    }

    /** Corre un comando como root; null si no hay root o falla. */
    private static String su(String cmd) {
        try {
            Process p = Runtime.getRuntime().exec(new String[] {"su", "-c", cmd});
            StringBuilder out = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
                String line;
                while ((line = r.readLine()) != null) out.append(line).append('\n');
            }
            return p.waitFor() == 0 ? out.toString() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private void toast(String msg) {
        runOnUiThread(() -> {
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
            finish();
        });
    }
}
