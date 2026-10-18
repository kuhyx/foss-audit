#!/bin/bash
# shellcheck shell=bash
#
# apksigner for foss_android_sdk.sh: AOSP's platform/tools/apksig (Apache-2.0)
# compiled with OpenJDK into build-tools/<ver>/lib/apksigner.jar. The
# BEGIN-AOSP/END-AOSP blocks only register conscrypt, a native provider for
# RSA-PSS; the JDK's own providers cover every scheme APKs are signed with,
# and AOSP's own Gradle build of apksig drops the same blocks. The AWS/GCP
# KMS signer backends need the cloud SDKs and are left out.
# Sourced, not executed.
#
# Expects from the caller: CACHE, JDK and a `die` function.

readonly APKSIG_REF=refs/tags/android-16.0.0_r1
readonly APKSIG_URL="https://android.googlesource.com/platform/tools/apksig/+archive/${APKSIG_REF}/src.tar.gz"

# Build apksigner into <build-tools dir>, with the launcher Google ships beside it.
build_apksigner() {
	local dir="$1" work
	work="$(mktemp -d "${CACHE}/apksig.XXXX")"
	curl -fsSL "$APKSIG_URL" | tar xz -C "$work" || die "could not fetch $APKSIG_URL"
	sed -i '/BEGIN-AOSP/,/END-AOSP/d' "${work}/apksigner/java/com/android/apksigner/ApkSignerTool.java"
	mkdir -p "${work}/classes" "${dir}/lib"
	find "${work}/main/java" "${work}/apksigner/java" -name '*.java' \
		-not -path '*/apksig/kms/aws/*' -not -path '*/apksig/kms/gcp/*' >"${work}/sources"
	"${JDK}/bin/javac" -nowarn -encoding UTF-8 --release 11 -d "${work}/classes" "@${work}/sources" >/dev/null ||
		die "javac failed for apksig"
	(cd "${work}/apksigner/java" && find . -name '*.txt' -exec cp --parents {} "${work}/classes/" \;)
	"${JDK}/bin/jar" --create --file "${dir}/lib/apksigner.jar" \
		--main-class com.android.apksigner.ApkSignerTool -C "${work}/classes" .
	# shellcheck disable=SC2016 # $0 and $@ belong to the launcher
	printf '#!/bin/sh\n# AOSP apksigner (Apache-2.0), built by foss_android_sdk.sh.\nexec "%s/bin/java" -jar "$(dirname "$(readlink -f "$0")")/lib/apksigner.jar" "$@"\n' \
		"$JDK" >"${dir}/apksigner"
	chmod +x "${dir}/apksigner"
	rm -rf "$work"
}
