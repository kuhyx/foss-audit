#!/bin/bash
# Assemble a Google-free Android SDK for Gradle/Flutter builds, and run Gradle
# against it with Google's SDK hidden, to prove nothing is read from it.
#
#   foss_android_sdk.sh assemble [api...]        build $FOSS_SDK
#   foss_android_sdk.sh gradle <android-dir> <task> [gradle args...]
#   foss_android_sdk.sh hidden <cmd...>          Google's SDK replaced by an empty dir
#
# Sources (all free): platform = Robolectric's android-all jar from Maven
# Central (AOSP framework, Apache-2.0); java.* for javac's system modules =
# OpenJDK (GPL-2.0 WITH Classpath-exception-2.0) plus android-all's libcore;
# build-tools = lzhiyong/android-sdk-tools (AOSP source, Apache-2.0) plus
# apksigner compiled from AOSP's apksig;
# cmake, platform-tools = Arch's cmake/ninja and android-tools. The NDK
# comes from foss_android_ndk.sh.
# Needs: curl, sha1sum, unzip, jmod/jar (OpenJDK), unshare (util-linux).
set -euo pipefail

readonly FOSS_SDK="${FOSS_SDK:-$HOME/sdk/foss-android-sdk}"
readonly GOOGLE_SDK="${GOOGLE_SDK:-$HOME/sdk/Android/Sdk}"
readonly CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/foss-android-sdk"
readonly JDK="${JDK:-/usr/lib/jvm/java-21-openjdk}"
readonly TOOLS="$HOME/.local/share/android-sdk-tools/build-tools"
HERE="$(cd "$(dirname "$0")" && pwd)"
readonly HERE
# shellcheck source=scripts/lib/foss_android_apksigner.sh
source "${HERE}/lib/foss_android_apksigner.sh"
# API level -> android-all release (its version starts with the Android
# release: 14 = API 34). Apps and plugins each pick a compileSdk.
declare -rA ANDROID_ALL=([34]=14-robolectric-10818077 [35]=15-robolectric-13954326
	[36]=16-robolectric-13921718 [37]=17-robolectric-15733970)
readonly BUILD_TOOLS_VER=36.0.0
# AGP's default externalNativeBuild CMake version.
readonly CMAKE_VER=3.22.1
readonly MAVEN=https://repo1.maven.org/maven2/org/robolectric/android-all
# What Google's core-for-system-modules.jar holds, by source: java.* from
# OpenJDK modules, the Android-specific libcore packages from android-all.
readonly JDK_MODULES=(java.base java.logging java.prefs java.sql java.xml)
# The classes in Google's build-tools core-lambda-stubs.jar.
readonly LAMBDA_STUBS=(CallSite LambdaConversionException LambdaMetafactory MethodHandle MethodHandles\$Lookup
	MethodHandles MethodType SerializedLambda StringConcatException StringConcatFactory)
readonly ANDROID_LIBCORE=(android/crypto android/icu android/net/ssl android/system dalvik org/json org/w3c org/xml org/xmlpull)

die() {
	echo "foss_android_sdk: $*" >&2
	exit 1
}

# Download android-all once and check it against Maven Central's SHA-1.
fetch_android_all() {
	local ver="$1"
	local jar="${CACHE}/android-all-${ver}.jar"
	local url="${MAVEN}/${ver}/android-all-${ver}.jar"
	mkdir -p "$CACHE"
	if [[ ! -f $jar ]]; then
		curl -fsSL -o "${jar}.part" "$url"
		mv "${jar}.part" "$jar"
	fi
	local want
	want="$(curl -fsSL "${url}.sha1")"
	echo "${want%% *}  ${jar}" | sha1sum -c --quiet - || die "SHA-1 mismatch for $jar"
	printf '%s' "$jar"
}

# package.xml for a local package; no <uses-license>: nothing here is Google's.
package_xml() {
	local path="$1" details="$2" revision="$3" name="$4"
	cat <<EOF
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ns2:repository xmlns:ns2="http://schemas.android.com/repository/android/common/02" xmlns:ns5="http://schemas.android.com/repository/android/generic/02" xmlns:ns8="http://schemas.android.com/sdk/android/repo/repository2/03"><localPackage path="${path}" obsolete="false">${details}<revision>${revision}</revision><display-name>${name}</display-name></localPackage></ns2:repository>
EOF
}

# Android's java.* (libcore) for javac and kotlinc: OpenJDK's java.* and
# javax.*, overlaid with the Android-only libcore packages from android-all.
# Only the package roots Google's own jars carry: AGP turns every directory
# of core-for-system-modules.jar into an export, and an empty one (jdk/,
# com/sun/...) fails its module-info compile.
build_libcore() {
	local android_all="$1" classes="$2" module work
	work="$(mktemp -d "${CACHE}/modules.XXXX")"
	mkdir -p "$classes"
	for module in "${JDK_MODULES[@]}"; do
		jmod extract --dir "${work}/${module}" "${JDK}/jmods/${module}.jmod"
		cp -r "${work}/${module}/classes/." "$classes/"
	done
	rm -rf "$work" "${classes}/module-info.class" "${classes}/org/jcp"
	# Older releases lack some packages (API 34 has no android.crypto):
	# unzip's 11 means "a pattern matched nothing", which is fine here.
	local rc=0
	unzip -qo "$android_all" "${ANDROID_LIBCORE[@]/%//*}" -d "$classes" 2>/dev/null || rc=$?
	((rc == 0 || rc == 11)) || die "unzip failed ($rc) on $android_all"
}

# Flutter only accepts an SDK dir holding platform-tools/ (or licenses/);
# Arch's android-tools (Apache-2.0, built from AOSP) provides adb/fastboot.
assemble_platform_tools() {
	local dir="${FOSS_SDK}/platform-tools" tool major minor micro
	mkdir -p "$dir"
	for tool in adb fastboot; do
		[[ -x "/usr/bin/${tool}" ]] || die "missing /usr/bin/${tool}; pacman -S android-tools"
		ln -sf "/usr/bin/${tool}" "${dir}/${tool}"
	done
	# Without package.xml AGP tries to download Google's platform-tools.
	IFS=. read -r major minor micro _ < <(pacman -Q android-tools | cut -d' ' -f2)
	package_xml platform-tools \
		'<type-details xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns5:genericDetailsType"/>' \
		"<major>${major}</major><minor>${minor}</minor><micro>${micro}</micro>" \
		"Platform-Tools (Arch android-tools)" >"${dir}/package.xml"
}

# AGP looks for the CMake version a module asks for (default 3.22.1) under
# $SDK/cmake/<ver>; Arch's cmake and ninja (BSD-3, Apache-2.0) stand in.
assemble_cmake() {
	local dir="${FOSS_SDK}/cmake/${CMAKE_VER}" tool
	mkdir -p "${dir}/bin"
	for tool in cmake ctest ninja; do
		ln -sf "/usr/bin/${tool}" "${dir}/bin/${tool}"
	done
	printf 'Pkg.Desc = CMake (system %s)
Pkg.Revision = %s
' "$(cmake --version | head -1)" "$CMAKE_VER" \
		>"${dir}/source.properties"
	package_xml "cmake;${CMAKE_VER}" \
		'<type-details xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns5:genericDetailsType"/>' \
		"<major>${CMAKE_VER%%.*}</major><minor>$(cut -d. -f2 <<<"$CMAKE_VER")</minor><micro>${CMAKE_VER##*.}</micro>" \
		"CMake ${CMAKE_VER} (system cmake)" >"${dir}/package.xml"
}

assemble_platform() {
	local api="$1" android_all="$2" dir="${FOSS_SDK}/platforms/android-$1"
	mkdir -p "${dir}/optional"
	unzip -qo "$android_all" build.prop -d "$dir"
	local classes="${CACHE}/libcore-${api}"
	rm -rf "$classes"
	build_libcore "$android_all" "$classes"
	# zip -D: no directory entries, which AGP would export as packages.
	rm -f "${dir}/core-for-system-modules.jar"
	(cd "$classes" && zip -qrD "${dir}/core-for-system-modules.jar" .)
	# kotlinc/lint read java.* from android.jar, as in Google's. OpenJDK's java.* name jdk.internal.*
	# and sun.* internally, so those go in too or L8 fails: "Missing class jdk.internal.loader.NativeLibrary".
	cp "$android_all" "${dir}/android.jar"
	"${JDK}/bin/jar" --update --file "${dir}/android.jar" -C "$classes" java -C "$classes" javax -C "$classes" jdk -C "$classes" sun
	python3 -I "${HERE}/foss_android_jar_nullability.py" "${dir}/android.jar"
	rm -rf "$classes" && : >"${dir}/framework.aidl" && echo '[]' >"${dir}/optional/optional.json"
	printf 'Pkg.Desc=FOSS Android Platform %s\nPkg.Revision=1\nAndroidVersion.ApiLevel=%s\nLayoutlib.Api=15\n' \
		"$api" "$api" >"${dir}/source.properties"
	package_xml "platforms;android-${api}" \
		"<type-details xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:type=\"ns8:platformDetailsType\"><api-level>${api}</api-level><codename></codename><base-extension>true</base-extension><layoutlib api=\"15\"/></type-details>" \
		"<major>1</major>" "FOSS Android Platform ${api} (android-all ${ANDROID_ALL[$api]})" >"${dir}/package.xml"
}

# D8 desugars lambdas, string concat and switch patterns against these
# signatures; OpenJDK's own java.lang.invoke classes carry the same ones.
build_lambda_stubs() {
	local out="$1" work name
	work="$(mktemp -d "${CACHE}/lambda.XXXX")"
	jmod extract --dir "$work" "${JDK}/jmods/java.base.jmod"
	local -a members=(-C "${work}/classes" java/lang/runtime/SwitchBootstraps.class)
	for name in "${LAMBDA_STUBS[@]}"; do
		members+=(-C "${work}/classes" "java/lang/invoke/${name}.class")
	done
	"${JDK}/bin/jar" --create --file "$out" "${members[@]}"
	rm -rf "$work"
}

assemble_build_tools() {
	local dir="${FOSS_SDK}/build-tools/${BUILD_TOOLS_VER}" major minor micro
	[[ -x "${TOOLS}/aapt2" ]] || die "missing ${TOOLS}; install lzhiyong/android-sdk-tools first"
	IFS=. read -r major minor micro <<<"$BUILD_TOOLS_VER"
	mkdir -p "$dir"
	cp "${TOOLS}"/* "$dir/"
	mv "${dir}/aapt2" "${dir}/aapt2.bin"
	install -m 755 "${HERE}/foss_aapt2_wrapper.sh" "${dir}/aapt2"
	build_apksigner "$dir"
	build_lambda_stubs "${dir}/core-lambda-stubs.jar"
	printf 'Pkg.Desc=FOSS Build-Tools (lzhiyong/android-sdk-tools)\nPkg.Revision=%s\n' \
		"$BUILD_TOOLS_VER" >"${dir}/source.properties"
	package_xml "build-tools;${BUILD_TOOLS_VER}" \
		'<type-details xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns5:genericDetailsType"/>' \
		"<major>${major}</major><minor>${minor}</minor><micro>${micro}</micro>" \
		"FOSS Build-Tools ${BUILD_TOOLS_VER}" >"${dir}/package.xml"
}

# One call per API keeps each download and build short; default: all.
cmd_assemble() {
	local api android_all
	local -a apis=("$@")
	((${#apis[@]})) || apis=("${!ANDROID_ALL[@]}")
	for api in "${apis[@]}"; do
		[[ -n ${ANDROID_ALL[$api]:-} ]] || die "no android-all release mapped for API $api"
		android_all="$(fetch_android_all "${ANDROID_ALL[$api]}")"
		assemble_platform "$api" "$android_all"
	done
	assemble_build_tools
	assemble_cmake
	assemble_platform_tools
	du -sh "$FOSS_SDK"
}

# Gradle inside a private user+mount namespace: Google's SDK path is covered
# by the FOSS SDK (bind mount), so any read of it gets the free files only.
cmd_gradle() {
	local dir="${1:?android project dir}" task="${2:?gradle task}"
	shift 2
	[[ -d $FOSS_SDK ]] || die "no $FOSS_SDK; run: $0 assemble"
	# The AUR flutter-bin SDK is a unionfs FUSE mount; mount it out here so
	# the namespace inherits it.
	local flutter_sdk
	flutter_sdk="$(sed -n 's/^flutter\.sdk=//p' "${dir}/local.properties")"
	[[ -x "${flutter_sdk}/bin/flutter" ]] || flutter --version >/dev/null
	# A unionfs started inside a transient scope (capped.sh) dies with it.
	[[ -f "${flutter_sdk}/packages/flutter_tools/gradle/src/main/scripts/CMakeLists.txt" ]] ||
		die "${flutter_sdk} is not mounted; run \`flutter --version\` outside capped.sh first"
	# An injected ABI makes AGP mark the APK testOnly, which adb install refuses.
	local -a extra=(--no-daemon)
	[[ " $* " != *" -Pandroid.injected.build.abi="* ]] || extra+=(-Pandroid.injected.testOnly=false)
	export ANDROID_HOME="$GOOGLE_SDK" ANDROID_SDK_ROOT="$GOOGLE_SDK"
	covered "$FOSS_SDK" "${dir}/gradlew" -p "$dir" --console=plain -Dorg.gradle.jvmargs=-Xmx3G \
		"${extra[@]}" "$task" "$@"
}

# Run a command with <cover> bind-mounted over Google's SDK, in a user+mount
# namespace. Root in the outer namespace may mount; the nested one maps back
# to our uid so the JVM finds $HOME (getpwuid) instead of /root.
covered() {
	local cover="$1"
	shift
	# shellcheck disable=SC2016 # $0, $1 and $@ belong to the inner sh
	unshare --user --map-root-user --mount \
		sh -c 'mount --bind "$0" "$1" && shift && exec "$@"' "$cover" "$GOOGLE_SDK" \
		unshare --user --map-user="$(id -u)" --map-group="$(id -g)" "$@"
}

# An EMPTY directory over Google's SDK: proves a configured build reads only
# $FOSS_SDK, since any leftover reference to Google's path finds nothing.
cmd_hidden() {
	local empty rc=0
	empty="$(mktemp -d)"
	covered "$empty" "$@" || rc=$?
	rmdir "$empty"
	return "$rc"
}

case "${1:-}" in
assemble) cmd_assemble "${@:2}" ;;
gradle) cmd_gradle "${@:2}" ;;
hidden) cmd_hidden "${@:2}" ;;
*) die "usage: $0 assemble [api...] | gradle <android-dir> <task> [args...] | hidden <cmd...>" ;;
esac
