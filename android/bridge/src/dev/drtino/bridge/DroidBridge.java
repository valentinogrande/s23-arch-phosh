package dev.drtino.bridge;

import android.content.Context;
import android.content.ContextWrapper;
import android.content.pm.ApplicationInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Looper;
import android.os.SystemClock;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Puente Android → Linux nativo, corre como root con app_process (sin app ni Context real).
 *  - Audio: lee PCM s16le 48 kHz estéreo de un FIFO (lo escribe PipeWire) y lo reproduce
 *    con AudioTrack, así el sonido sale por el audio de Android.
 *  - Rotación: lee el acelerómetro de Android y escribe la orientación (normal, left-up,
 *    right-up, bottom-up; nombres de iio-sensor-proxy) en un archivo.
 * Uso: app_process / dev.drtino.bridge.DroidBridge AUDIO_FIFO ORIENT_FILE
 */
public class DroidBridge {
    private static final int RATE = 48000;

    public static void main(String[] args) throws Exception {
        String fifo = args[0];
        String orientFile = args[1];
        Thread audio = new Thread(() -> audioLoop(fifo), "audio");
        audio.setDaemon(true);
        audio.start();

        Looper.prepareMainLooper();
        try {
            startSensors(orientFile);
        } catch (Throwable t) {
            System.err.println("sensores: " + t);
        }
        Looper.loop();
    }

    // ── Audio ────────────────────────────────────────────────────────────────

    private static void audioLoop(String fifo) {
        int min = AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_STEREO,
                AudioFormat.ENCODING_PCM_16BIT);
        AudioTrack track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build())
                .setAudioFormat(new AudioFormat.Builder()
                        .setSampleRate(RATE)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build())
                .setBufferSizeInBytes(min * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build();
        System.err.println("audio: AudioTrack listo, buffer " + min * 2);
        byte[] buf = new byte[min];
        while (true) {
            // open() bloquea hasta que PipeWire abre el FIFO para escribir; EOF = lo cerró.
            try (InputStream in = new FileInputStream(fifo)) {
                track.play();
                int n;
                while ((n = in.read(buf)) > 0) {
                    track.write(buf, 0, n & ~3);
                }
            } catch (IOException e) {
                System.err.println("audio: " + e);
                SystemClock.sleep(1000);
            }
            track.pause();
            track.flush();
        }
    }

    // ── Rotación ─────────────────────────────────────────────────────────────

    /** Lo mínimo que SystemSensorManager le pide a un Context. */
    static class FakeContext extends ContextWrapper {
        FakeContext() {
            super(null);
        }

        @Override public String getPackageName() { return "com.android.shell"; }
        @Override public String getOpPackageName() { return "com.android.shell"; }
        @Override public String getAttributionTag() { return null; }
        @Override public Context getApplicationContext() { return this; }
        @Override public int getDeviceId() { return Context.DEVICE_ID_DEFAULT; }

        @Override
        public ApplicationInfo getApplicationInfo() {
            ApplicationInfo ai = new ApplicationInfo();
            ai.packageName = getPackageName();
            ai.targetSdkVersion = 36;
            return ai;
        }
    }

    private static void startSensors(String orientFile) throws Exception {
        SensorManager sm = (SensorManager) Class.forName("android.hardware.SystemSensorManager")
                .getConstructor(Context.class, Looper.class)
                .newInstance(new FakeContext(), Looper.getMainLooper());
        Sensor accel = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
        if (accel == null) {
            System.err.println("sensores: no hay acelerómetro");
            return;
        }
        sm.registerListener(new SensorEventListener() {
            String current = "";
            String candidate = "";
            long since;

            @Override
            public void onSensorChanged(SensorEvent e) {
                String o = orientation(e.values[0], e.values[1], e.values[2]);
                if (o == null) return;
                long now = SystemClock.uptimeMillis();
                if (!o.equals(candidate)) {
                    candidate = o;
                    since = now;
                }
                // Medio segundo estable antes de rotar, como Android.
                if (!o.equals(current) && now - since > 500) {
                    current = o;
                    writeAtomic(orientFile, o + "\n");
                }
            }

            @Override
            public void onAccuracyChanged(Sensor s, int a) {}
        }, accel, SensorManager.SENSOR_DELAY_UI);
        System.err.println("sensores: acelerómetro " + accel.getName());
    }

    /** Gravedad → orientación; null si está casi plano o en un ángulo dudoso. */
    static String orientation(float x, float y, float z) {
        if (Math.abs(z) > 8.0f) return null;
        if (y > 6.5f) return "normal";
        if (y < -6.5f) return "bottom-up";
        if (x > 6.5f) return "right-up";
        if (x < -6.5f) return "left-up";
        return null;
    }

    static void writeAtomic(String path, String text) {
        File tmp = new File(path + ".tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(text.getBytes());
        } catch (IOException e) {
            System.err.println("orientación: " + e);
            return;
        }
        tmp.renameTo(new File(path));
    }
}
