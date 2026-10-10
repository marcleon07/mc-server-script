#!/usr/bin/env bash
# Builds ServerLink.jar from src/ and res/ without Maven (needs a JDK 21+).
# usage: ./build.sh [Paper libraries folder]
#   The Paper API comes from a Paper server's libraries/ folder (default: ../../lobby-server/libraries).
#   With Maven instead: mvn package   (-> target/ServerLink.jar)
set -euo pipefail
cd "$(dirname "$0")"
LIBS="${1:-../../lobby-server/libraries}"
[ -d "$LIBS" ] || { echo "no Paper libraries folder at $LIBS - pass one, or build with: mvn package" >&2; exit 1; }

BIN=""
if [ -n "${JAVA_HOME:-}" ]; then BIN="$JAVA_HOME/bin/"
elif ! command -v javac >/dev/null; then
  for d in "/c/Program Files/Eclipse Adoptium"/jdk-*/bin; do [ -x "$d/javac.exe" ] && BIN="$d/"; done
fi
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) SEP=';' ;; *) SEP=':' ;; esac
CP=$(find "$LIBS" -name '*.jar' | tr '\n' "$SEP")

rm -rf build && mkdir -p build
"${BIN}javac" -nowarn --release 21 -cp "$CP" -d build src/dev/mcserver/serverlink/*.java
cp res/* build/
(cd build && "${BIN}jar" cf ../ServerLink.jar .)
echo built ServerLink.jar
