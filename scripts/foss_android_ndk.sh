#!/bin/bash
# Assemble a Google-free NDK under $FOSS_SDK/ndk/<ver> for C native builds
# (package:jni and the like): Arch's clang/lld, the NDK's CMake toolchain
# files (AOSP platform/ndk), a bionic sysroot made from AOSP sources
# (headers, ndkstubgen stub libraries, crt objects), and compiler-rt builtins
# plus libunwind and libc++ built from llvm-project at Arch's clang version.
#
#   foss_android_ndk.sh fetch | unpack-llvm | sysroot | builtins | unwind | toolchain
#     | libcxx-configure | libcxx-build <part> <parts> | libcxx-install
#
# Each phase stays under a minute; run them in that order. arm64-v8a only.
# Needs: curl, tar, gh, python3, clang, lld, llvm, cmake, ninja.
set -euo pipefail

readonly FOSS_SDK="${FOSS_SDK:-$HOME/sdk/foss-android-sdk}"
readonly CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/foss-android-ndk"
readonly SRC="${CACHE}/src"
# Flutter 3.47's flutter.ndkVersion, so AGP finds it without a local.properties edit.
readonly NDK_VER=28.2.13676358
readonly NDK="${FOSS_SDK}/ndk/${NDK_VER}"
readonly TC="${NDK}/toolchains/llvm/prebuilt/linux-x86_64"
readonly SYSROOT="${TC}/sysroot"
readonly AOSP=https://android.googlesource.com
readonly AOSP_REF=refs/tags/android-16.0.0_r1
readonly NDK_REF=refs/heads/ndk-r28-release
readonly ARCH=arm64 TRIPLE=aarch64-linux-android
readonly API_MIN=21 API_MAX=35
readonly STUB_LIBS=(c m dl log)
# Soong builds these NDK stubs without symbol versions (unversioned_until),
# so binaries do not demand a version node older devices may lack.
readonly UNVERSIONED_LIBS=" log "
LLVM_VER="$(clang -dumpversion)"
readonly LLVM_VER LLVM_MAJOR="${LLVM_VER%%.*}"
readonly LLVM_SRC="${SRC}/llvm-project-${LLVM_VER}.src"
readonly RESOURCE_DIR="${TC}/lib/clang/${LLVM_MAJOR}"
HERE="$(cd "$(dirname "$0")" && pwd)"
readonly HERE
# shellcheck source=scripts/lib/foss_android_ndk_runtimes.sh
source "${HERE}/lib/foss_android_ndk_runtimes.sh"

die() {
	echo "foss_android_ndk: $*" >&2
	exit 1
}

# A directory of an AOSP project at a ref, via gitiles' per-directory tarball.
aosp_dir() {
	local project="$1" ref="$2" path="$3" dest="${SRC}/$4"
	mkdir -p "$dest"
	curl -fsS "${AOSP}/${project}/+archive/${ref}/${path}.tar.gz" | tar xz -C "$dest"
}

# One file of an AOSP project (gitiles serves it base64-encoded).
aosp_file() {
	local project="$1" path="$2" dest="${SRC}/$3"
	mkdir -p "$(dirname "$dest")"
	curl -fsS "${AOSP}/${project}/+/${AOSP_REF}/${path}?format=TEXT" | base64 -d >"$dest"
}

cmd_fetch() {
	rm -rf "$SRC" && mkdir -p "$SRC"
	local d
	for d in libc/include libc/kernel/uapi libc/kernel/android/uapi libc/arch-common/bionic libc/private; do
		aosp_dir platform/bionic "$AOSP_REF" "$d" "bionic/$d"
	done
	aosp_file platform/bionic libc/bionic/libc_init_common.h bionic/libc/bionic/libc_init_common.h
	for d in libc/libc libm/libm libdl/libdl; do
		aosp_file platform/bionic "${d}.map.txt" "bionic/${d}.map.txt"
	done
	aosp_dir platform/system/logging "$AOSP_REF" liblog/include logging/include
	aosp_file platform/system/logging liblog/liblog.map.txt logging/liblog.map.txt
	aosp_dir platform/libnativehelper "$AOSP_REF" include_jni nativehelper
	aosp_dir platform/build/soong "$AOSP_REF" cc/ndkstubgen soong/ndkstubgen
	aosp_dir platform/build/soong "$AOSP_REF" cc/symbolfile soong/symbolfile
	aosp_dir platform/ndk "$NDK_REF" build/cmake ndk/build/cmake
	aosp_dir platform/ndk "$NDK_REF" meta ndk/meta
	local tarball="llvm-project-${LLVM_VER}.src.tar.xz"
	local release="https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VER}"
	curl -fsSL -o "${CACHE}/${tarball}" "${release}/${tarball}"
	# The release's sigstore attestation proves the tarball came from llvm's CI.
	curl -fsSL -o "${CACHE}/${tarball}.jsonl" "${release}/${tarball}.jsonl"
	gh attestation verify "${CACHE}/${tarball}" --bundle "${CACHE}/${tarball}.jsonl" \
		--repo llvm/llvm-project >/dev/null || die "attestation check failed for $tarball"
	printf 'AOSP %s (bionic, logging, libnativehelper, soong)\nAOSP platform/ndk %s\nllvm-project %s\n' \
		"$AOSP_REF" "$NDK_REF" "$LLVM_VER" >"${SRC}/SOURCES"
}

# Only the runtimes' sources: decompressing the whole tree is most of a minute.
cmd_unpack_llvm() {
	local top="llvm-project-${LLVM_VER}.src"
	rm -rf "$LLVM_SRC"
	tar -xJf "${CACHE}/${top}.tar.xz" -C "$SRC" --wildcards \
		"${top}/compiler-rt/*" "${top}/libunwind/*" "${top}/cmake/*" "${top}/runtimes/*" \
		"${top}/llvm/cmake/*" "${top}/llvm/utils/llvm-lit/*" "${top}/third-party/*" "${top}/libcxx/*" "${top}/libcxxabi/*" "${top}/libc/*"
}

sysroot_headers() {
	local inc="${SYSROOT}/usr/include" uapi="${SRC}/bionic/libc/kernel/uapi" d
	rm -rf "$inc" && mkdir -p "${inc}/${TRIPLE}"
	cp -r "${SRC}/bionic/libc/include/." "$inc/"
	for d in "$uapi"/*; do
		[[ $(basename "$d") == asm-* ]] || cp -r "$d" "$inc/"
	done
	cp -r "${uapi}/asm-generic" "$inc/"
	# Bionic's own additions to the kernel headers (linux/compiler_types.h).
	cp -r "${SRC}/bionic/libc/kernel/android/uapi/." "$inc/"
	cp -r "${uapi}/asm-${ARCH}/asm" "${inc}/${TRIPLE}/"
	cp -r "${SRC}/logging/include/android/." "${inc}/android/"
	cp "${SRC}/nativehelper/jni.h" "$inc/"
}

# Stub shared libraries: the exported symbols of each NDK API level, no code.
build_stubs() {
	local api="$1" out="$2" lib map work
	work="$(mktemp -d "${CACHE}/stubs.XXXX")"
	declare -A maps=([c]=bionic/libc/libc.map.txt [m]=bionic/libm/libm.map.txt
		[dl]=bionic/libdl/libdl.map.txt [log]=logging/liblog.map.txt)
	local -a version
	for lib in "${STUB_LIBS[@]}"; do
		map="${SRC}/${maps[$lib]}"
		version=("-Wl,--version-script=${work}/${lib}.map")
		[[ $UNVERSIONED_LIBS != *" ${lib} "* ]] || version=()
		PYTHONPATH="${SRC}/soong" python3 "${SRC}/soong/ndkstubgen/__init__.py" \
			--arch "$ARCH" --api "$api" --api-map "${HERE}/foss_android_api_levels.json" \
			"$map" "${work}/${lib}.c" "${work}/${lib}.map" "${work}/${lib}.syms"
		# Stub cflags as AOSP builds NDK stubs: the declarations are deliberately bogus.
		clang --target="${TRIPLE}${api}" -fuse-ld=lld -shared -nostdlib -fPIC -O0 -fno-builtin -fno-unwind-tables \
			-Wno-incompatible-library-redeclaration -Wno-incomplete-setjmp-declaration \
			-Wno-builtin-requires-header -Wno-invalid-noreturn \
			"${version[@]}" -Wl,-soname,"lib${lib}.so" \
			-o "${out}/lib${lib}.so" "${work}/${lib}.c"
	done
	rm -rf "$work"
}

# crt objects as bionic builds them: crtbrand's ELF note carries the API level.
build_crt() {
	local api="$1" out="$2" bionic="${SRC}/bionic/libc/arch-common/bionic" work
	work="$(mktemp -d "${CACHE}/crt.XXXX")"
	local -a cc=(clang --target="${TRIPLE}${api}" --sysroot="$SYSROOT" -fPIC -O2 -fno-stack-protector
		-DPLATFORM_SDK_VERSION="$api" -I"${SRC}/bionic/libc" -I"$bionic" -c)
	local src
	for src in crtbegin.c crtbegin_so.c crtbrand.S crtend.S crtend_so.S crt_pad_segment.S; do
		"${cc[@]}" "${bionic}/${src}" -o "${work}/${src%.*}.o"
	done
	ld.lld -r "${work}/crtbegin_so.o" "${work}/crtbrand.o" -o "${out}/crtbegin_so.o"
	ld.lld -r "${work}/crtbegin.o" "${work}/crtbrand.o" -o "${out}/crtbegin_dynamic.o"
	cp "${work}/crtend_so.o" "${out}/crtend_so.o"
	cp "${work}/crtend.o" "${out}/crtend_android.o"
	cp "${work}/crt_pad_segment.o" "${out}/crt_pad_segment.o"
	rm -rf "$work"
}

cmd_sysroot() {
	sysroot_headers
	local api out
	for ((api = API_MIN; api <= API_MAX; api++)); do
		out="${SYSROOT}/usr/lib/${TRIPLE}/${api}"
		rm -rf "$out" && mkdir -p "$out"
		build_stubs "$api" "$out"
		build_crt "$api" "$out"
	done
}

# clang wrappers, not symlinks: clang derives its resource dir from the real
# binary's path and would never look in this NDK for the Android runtimes.
write_wrapper() {
	local name="$1" target="$2"
	printf '#!/bin/sh\n# FOSS NDK: system %s with this NDK'"'"'s resource dir, sysroot and lld.\nexec %s -resource-dir "%s" --sysroot="%s" -fuse-ld=lld -Wno-unused-command-line-argument "$@"\n' \
		"$target" "$target" "$RESOURCE_DIR" "$SYSROOT" >"${TC}/bin/${name}"
	chmod +x "${TC}/bin/${name}"
}

cmd_toolchain() {
	mkdir -p "${TC}/bin" "${RESOURCE_DIR}" "${NDK}/build"
	ln -sfn "/usr/lib/clang/${LLVM_MAJOR}/include" "${RESOURCE_DIR}/include"
	# The NDK's toolchain file links -latomic; the __atomic_* calls live in
	# the builtins, so this is an empty linker script, as in the NDK.
	mkdir -p "${RESOURCE_DIR}/lib/linux/aarch64"
	echo '/* __atomic_* are in libclang_rt.builtins (see llvm.org/D47606). */' \
		| tee "${RESOURCE_DIR}/lib/linux/aarch64/libatomic.a" >"${SYSROOT}/usr/lib/${TRIPLE}/libatomic.a"
	write_wrapper clang /usr/bin/clang
	write_wrapper clang++ /usr/bin/clang++
	local tool
	for tool in ld.lld lld llvm-ar llvm-ranlib llvm-strip llvm-objcopy llvm-nm llvm-readelf llvm-objdump llvm-as; do
		ln -sf "/usr/bin/${tool}" "${TC}/bin/${tool}"
	done
	rm -rf "${NDK}/build/cmake" "${NDK}/meta"
	cp -r "${SRC}/ndk/build/cmake" "${NDK}/build/cmake"
	cp -r "${SRC}/ndk/meta" "${NDK}/meta"
	local -a libs=()
	for tool in "${STUB_LIBS[@]}"; do libs+=("lib${tool}.so:${API_MIN}"); done
	python3 "${HERE}/foss_android_ndk_meta.py" "$NDK" "$LLVM_VER" "${libs[@]}"
	# The toolchain file parses exactly "Pkg.Desc = Android NDK" + revision.
	printf 'Pkg.Desc = Android NDK\nPkg.Revision = %s\n# FOSS NDK: system LLVM %s, AOSP bionic sysroot; see SOURCES\n' \
		"$NDK_VER" "$LLVM_VER" >"${NDK}/source.properties"
	cp "${SRC}/SOURCES" "${NDK}/SOURCES"
}

case "${1:-}" in
fetch) cmd_fetch ;;
unpack-llvm) cmd_unpack_llvm ;;
sysroot) cmd_sysroot ;;
builtins) cmd_builtins ;;
unwind) cmd_unwind ;;
toolchain) cmd_toolchain ;;
libcxx-configure) cmd_libcxx_configure ;;
libcxx-build) cmd_libcxx_build "${@:2}" ;;
libcxx-install) cmd_libcxx_install ;;
*) die "usage: $0 fetch | unpack-llvm | sysroot | builtins | unwind | toolchain | libcxx-{configure,build,install}" ;;
esac
