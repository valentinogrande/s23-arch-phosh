#!/bin/bash
# Compila DroidBridge a un jar con classes.dex para app_process (sin APK).
set -e
cd "$(dirname "$0")"
SDK=$HOME/Android/Sdk
BT=$SDK/build-tools/36.0.0
JAR=$SDK/platforms/android-36/android.jar

rm -rf out && mkdir -p out/classes out/dex
javac --release 17 -cp $JAR -d out/classes $(find src -name '*.java')
$BT/d8 --min-api 33 --lib $JAR --output out/dex $(find out/classes -name '*.class')
(cd out/dex && zip -q ../bridge.jar classes.dex)
echo "JAR: $(pwd)/out/bridge.jar  ->  /data/local/arch-tools/bridge.jar"
