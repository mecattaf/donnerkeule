# Consumer-side packaging repair for a source pin that must remain frozen.
# Example: dotfiles #610 keeps fb05a7d while nixpkgs advances to 7.2.12.
# This imports that pin's module/source, without using the 7.3 driver changes.
{
  lib,
  kernelPackages,
  source,
}:
(kernelPackages.callPackage (source + "/nix/module.nix") { inherit source; }).overrideAttrs (old: {
  installPhase = ''
    runHook preInstall
    make ${lib.escapeShellArgs kernelPackages.kernelModuleMakeFlags} \
      KVER=${kernelPackages.kernel.modDirVersion} \
      KDIR=${kernelPackages.kernel.dev}/lib/modules/${kernelPackages.kernel.modDirVersion}/build \
      INSTALL_MOD_PATH="$out" INSTALL_MOD_DIR=extra \
      CONFIG_MODULE_COMPRESS_ALL= DEPMOD=true modules_install
    runHook postInstall
  '';
})
