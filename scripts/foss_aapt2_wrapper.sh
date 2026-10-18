#!/bin/sh
# Installed as build-tools/<ver>/aapt2 by foss_android_sdk.sh, in front of
# lzhiyong's aapt2 (aapt2.bin). Its option parser (AOSP 35.0.2, the newest
# release) rejects the --flag=value form AGP passes to `aapt2 optimize` and
# exits 1; AGP ignores that and packages an APK with no AndroidManifest.xml.
# Split such arguments into --flag value. Daemon mode (`aapt2 m`) reads its
# commands from stdin, which exec passes through untouched.
set -eu
for arg; do
	shift
	case $arg in
	--*=*) set -- "$@" "${arg%%=*}" "${arg#*=}" ;;
	*) set -- "$@" "$arg" ;;
	esac
done
exec "$(dirname "$0")/aapt2.bin" "$@"
