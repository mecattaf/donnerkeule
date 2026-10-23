{
  lib,
  stdenv,
  kernel,
  kernelModuleMakeFlags,
  source ? ../.,
  enableProfiling ? true,
}:

let
  root = source;
  rootPrefix = "${toString root}/";
  sourceEntries = [
    "Makefile"
    "include"
    "kernel"
    "proto"
  ];
in
stdenv.mkDerivation {
  pname = "thunderbolt-ibverbs";
  version = "0.4.0";

  src = lib.cleanSourceWith {
    src = root;
    filter =
      path: type:
      let
        rel = lib.removePrefix rootPrefix (toString path);
      in
      builtins.any (entry: rel == entry || lib.hasPrefix "${entry}/" rel) sourceEntries;
  };

  nativeBuildInputs = kernel.moduleBuildDependencies;

  buildPhase = ''
    runHook preBuild
    make \
      ${lib.escapeShellArgs kernelModuleMakeFlags} \
      TBV_PROFILING=${if enableProfiling then "1" else "0"} \
      KVER=${kernel.modDirVersion} \
      KDIR=${kernel.dev}/lib/modules/${kernel.modDirVersion}/build \
      modules
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    # Use Kbuild's install/signing rule. Newer nixpkgs aggregates external
    # modules' .ko.cer sidecars when it assembles the NixOS modules tree.
    make ${lib.escapeShellArgs kernelModuleMakeFlags} \
      KVER=${kernel.modDirVersion} \
      KDIR=${kernel.dev}/lib/modules/${kernel.modDirVersion}/build \
      INSTALL_MOD_PATH="$out" INSTALL_MOD_DIR=extra \
      CONFIG_MODULE_COMPRESS_ALL= DEPMOD=true modules_install
    runHook postInstall
  '';

  dontPatchELF = true;
  dontStrip = true;
  dontFixup = true;

  meta = {
    description = "Thunderbolt/USB4 host-to-host RDMA verbs kernel module";
    license = lib.licenses.gpl2Only;
    maintainers = with lib.maintainers; [ georgewhewell ];
    platforms = [ "x86_64-linux" ];
  };
}
