#!/bin/bash
# Build sin Gradle: aapt2 + javac + d8 + zipalign + apksigner.
set -e
cd "$(dirname "$0")"
SDK=$HOME/Android/Sdk
BT=$SDK/build-tools/36.0.0
JAR=$SDK/platforms/android-36/android.jar

rm -rf out && mkdir -p out/res out/classes out/dex
$BT/aapt2 compile --dir res -o out/res
$BT/aapt2 link -o out/unsigned.apk -I $JAR --manifest AndroidManifest.xml out/res/*.flat
javac --release 17 -cp $JAR -d out/classes $(find src -name '*.java')
$BT/d8 --min-api 33 --lib $JAR --output out/dex $(find out/classes -name '*.class')
(cd out/dex && zip -q ../unsigned.apk classes.dex)
$BT/zipalign -f 4 out/unsigned.apk out/aligned.apk
$BT/apksigner sign --ks $HOME/.android/debug.keystore --ks-pass pass:android \
    --out out/arch.apk out/aligned.apk
echo "APK: $(pwd)/out/arch.apk"
