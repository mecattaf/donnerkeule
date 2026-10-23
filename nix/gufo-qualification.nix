# Build only the no-model Gufo TP2 all-reduce probe, against this fork's
# provider. No GPU execution occurs during build or --help validation.
# nix build --impure --file nix/gufo-qualification.nix -o result-gufo-probe
let
  driver = builtins.getFlake "path:${toString ../.}";
  gufo = builtins.getFlake "github:neuhaus/gufo/c0beaa64361b6783b5a4894bbf96dab832c154f6";
  lib = driver.inputs.nixpkgs.lib;
  base = gufo.packages.x86_64-linux.tp2-rdma.override {
    rdma-core = driver.packages.x86_64-linux.rdma-core-usb4;
  };
in base.overrideAttrs (old: {
  pname = "gufo-tp2-qualification";
  postPatch = (old.postPatch or "") + ''
    cat >> CMakeLists.txt <<'EOF'
    add_executable(tbv_gufo_tp2_probe tests/models/qwen38_flash_next/tp_batched_probe.cpp)
    target_link_libraries(tbv_gufo_tp2_probe PRIVATE gufo_qwen38_flash_next hip::host)
    EOF
  '';
  ninjaFlags = [ "tbv_gufo_tp2_probe" ];
  installPhase = ''
    runHook preInstall
    install -D tbv_gufo_tp2_probe "$out/bin/tbv-gufo-tp2-probe"
    runHook postInstall
  '';
  postFixup = lib.replaceStrings [ "$out/bin/gufo" ] [ "$out/bin/tbv-gufo-tp2-probe" ] old.postFixup;
  installCheckPhase = ''
    "$out/bin/tbv-gufo-tp2-probe" --help | grep -q -- --allreduce-bench
  '';
})
