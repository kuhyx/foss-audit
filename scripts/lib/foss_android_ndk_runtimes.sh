#!/bin/bash
# shellcheck shell=bash
#
# LLVM runtimes for foss_android_ndk.sh: compiler-rt builtins, libunwind and
# libc++/libc++abi, cross-built from llvm-project at Arch's clang version.
# Sourced, not executed.
#
# Expects from the caller: CACHE, LLVM_SRC, RESOURCE_DIR, SYSROOT, NDK_ABI,
# TRIPLE, TARGET, PROCESSOR, RT_ARCH, API_MIN, API_MAX and a `die` function.

runtime_failed() {
	grep -B2 -A6 -m3 -E 'FAILED|error:|CMake Error' "${1}.log" >&2 || tail -20 "${1}.log" >&2
	die "runtime build failed; full log: ${1}.log"
}

# CMake for one runtime, cross-compiled with the system clang at API_MIN.
# CMake's own Android platform insists on an NDK, so this is a plain Linux
# cross build with ANDROID set by hand (what compiler-rt keys its naming on).
# The API level keeps LLVM from adding _FILE_OFFSET_BITS=64 on 32-bit ABIs:
# bionic only has fseeko64 and friends from API 24.
runtime_configure() {
	local src="$1" build="$2"
	shift 2
	rm -rf "$build"
	cmake -G Ninja -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR="$PROCESSOR" -DANDROID=1 -DANDROID_NATIVE_API_LEVEL="$API_MIN" \
		-DCMAKE_SYSROOT="$SYSROOT" -DCMAKE_MAKE_PROGRAM="$(command -v ninja)" \
		-DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_ASM_COMPILER=clang \
		-DCMAKE_C_COMPILER_TARGET="${TARGET}${API_MIN}" -DCMAKE_CXX_COMPILER_TARGET="${TARGET}${API_MIN}" \
		-DCMAKE_ASM_COMPILER_TARGET="${TARGET}${API_MIN}" -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
		-DCMAKE_AR="$(command -v llvm-ar)" -DCMAKE_RANLIB="$(command -v llvm-ranlib)" "$@" >"${build}.log" 2>&1 ||
		runtime_failed "$build"
}

runtime_cmake() {
	runtime_configure "$@"
	ninja -C "$2" >>"${2}.log" 2>&1 || runtime_failed "$2"
}

cmd_builtins() {
	local build="${CACHE}/build-builtins-${NDK_ABI}"
	local archive="${RESOURCE_DIR}/lib/linux/libclang_rt.builtins-${RT_ARCH}-android.a" probe
	runtime_cmake "${LLVM_SRC}/compiler-rt/lib/builtins" "$build" \
		-DCOMPILER_RT_DEFAULT_TARGET_ONLY=ON -DCOMPILER_RT_EXCLUDE_ATOMIC_BUILTIN=OFF -DLLVM_CMAKE_DIR="${LLVM_SRC}/llvm/cmake/modules"
	mkdir -p "${RESOURCE_DIR}/lib/linux"
	rm -f "$archive"
	find "$build" -name "libclang_rt.builtins*.a" -exec cp {} "$archive" \;
	[[ -s $archive ]] || die "builtins archive missing"
	# The driver must pick this flat name at every API level (per-target dirs
	# would embed the level), or it links nothing and every link fails late.
	for probe in "${API_MIN}" "${API_MAX}"; do
		[[ $(clang --target="${TARGET}${probe}" -resource-dir "$RESOURCE_DIR" -rtlib=compiler-rt \
			-print-libgcc-file-name) == "$archive" ]] || die "clang --target=${TARGET}${probe} does not resolve $archive"
	done
}

cmd_unwind() {
	local build="${CACHE}/build-unwind-${NDK_ABI}"
	# Static-library try-compiles never link, so every library probe passes;
	# bionic has pthreads in libc and a stray -lpthread breaks every C++ link.
	runtime_cmake "${LLVM_SRC}/runtimes" "$build" -DLLVM_ENABLE_RUNTIMES=libunwind \
		-DLIBUNWIND_HAS_PTHREAD_LIB=OFF -DLIBUNWIND_ENABLE_SHARED=OFF -DLIBUNWIND_USE_COMPILER_RT=ON -DLLVM_INCLUDE_TESTS=OFF \
		-DCMAKE_C_FLAGS=-rtlib=compiler-rt -DCMAKE_CXX_FLAGS="-rtlib=compiler-rt -nostdinc++" \
		-DCMAKE_C_FLAGS_INIT="-resource-dir=${RESOURCE_DIR}"
	cp "${build}/lib/libunwind.a" "${SYSROOT}/usr/lib/${TRIPLE}/libunwind.a"
}

readonly LIBCXX_BUILD="${CACHE}/build-libcxx-${NDK_ABI}"

# libc++ as the NDK ships it: the __ndk1 ABI namespace (so it never clashes
# with a platform libc++), unversioned c++_shared/c++_static, libc++abi apart in
# the static case and folded into the shared one. The unwinder comes from the
# clang driver (libunwind.a in the sysroot), as with the NDK's clang.
cmd_libcxx_configure() {
	local flags="-resource-dir=${RESOURCE_DIR} -rtlib=compiler-rt"
	# Bionic has __cxa_thread_atexit_impl from API 23; at API_MIN libc++abi
	# must reference it weakly (the probe passes, see cmd_unwind).
	runtime_configure "${LLVM_SRC}/runtimes" "$LIBCXX_BUILD" -DLLVM_ENABLE_RUNTIMES="libcxxabi;libcxx" \
		-DCMAKE_C_FLAGS="$flags" -DCMAKE_CXX_FLAGS="$flags -nostdinc++" -DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=lld \
		-DCMAKE_INSTALL_PREFIX="${LIBCXX_BUILD}-staging" -DLLVM_ENABLE_PER_TARGET_RUNTIME_DIR=OFF \
		-DLIBCXX_ABI_NAMESPACE=__ndk1 -DLIBCXX_CXX_ABI=libcxxabi \
		-DLIBCXX_SHARED_OUTPUT_NAME=c++_shared -DLIBCXX_STATIC_OUTPUT_NAME=c++_static \
		-DCMAKE_PLATFORM_NO_VERSIONED_SONAME=ON \
		-DLIBCXX_STATICALLY_LINK_ABI_IN_SHARED_LIBRARY=ON -DLIBCXX_STATICALLY_LINK_ABI_IN_STATIC_LIBRARY=OFF \
		-DLIBCXXABI_ENABLE_SHARED=OFF -DLIBCXXABI_USE_LLVM_UNWINDER=OFF -DLIBCXXABI_HAS_CXA_THREAD_ATEXIT_IMPL=OFF \
		-DLIBCXX_USE_COMPILER_RT=ON -DLIBCXXABI_USE_COMPILER_RT=ON \
		-DLLVM_INCLUDE_TESTS=OFF -DLIBCXX_INCLUDE_TESTS=OFF -DLIBCXXABI_INCLUDE_TESTS=OFF \
		-DLIBCXX_INCLUDE_BENCHMARKS=OFF -DLIBCXX_INCLUDE_DOCS=OFF
}

# Compile every <n>th object starting at <part> (1-based), so the build
# splits into calls that each stay under a minute.
cmd_libcxx_build() {
	local part="${1:?part}" parts="${2:?parts}"
	[[ -d $LIBCXX_BUILD ]] || die "run libcxx-configure first"
	local -a objs
	mapfile -t objs < <(ninja -C "$LIBCXX_BUILD" -t targets all | sed -n 's/^\([^:]*\.o\): .*/\1/p' |
		awk -v p="$part" -v n="$parts" 'NR % n == p % n')
	((${#objs[@]})) || die "no objects for part $part/$parts"
	ninja -C "$LIBCXX_BUILD" "${objs[@]}" >>"${LIBCXX_BUILD}.log" 2>&1 || runtime_failed "$LIBCXX_BUILD"
}

cmd_libcxx_install() {
	ninja -C "$LIBCXX_BUILD" install-cxx install-cxxabi >>"${LIBCXX_BUILD}.log" 2>&1 || runtime_failed "$LIBCXX_BUILD"
	local stage="${LIBCXX_BUILD}-staging" lib="${SYSROOT}/usr/lib/${TRIPLE}" name api
	rm -rf "${SYSROOT}/usr/include/c++"
	mkdir -p "${SYSROOT}/usr/include/c++"
	cp -r "${stage}/include/c++/v1" "${SYSROOT}/usr/include/c++/v1"
	for name in libc++_static.a libc++_shared.so libc++abi.a libc++experimental.a; do
		cp "${stage}/lib/${name}" "${lib}/${name}"
	done
	# -lc++ resolves per API level to these linker scripts, as in the NDK.
	for ((api = API_MIN; api <= API_MAX; api++)); do
		echo 'INPUT(-lc++_static -lc++abi)' >"${lib}/${api}/libc++.a"
		echo 'INPUT(-lc++_shared)' >"${lib}/${api}/libc++.so"
	done
}
