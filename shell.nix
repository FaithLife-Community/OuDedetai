let
  # We pin to a specific nixpkgs commit for reproducibility.
  # Last updated: 2025-02-10. Check for new commits at https://status.nixos.org.
  pkgs = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/a45fa362d887f4d4a7157d95c28ca9ce2899b70e.tar.gz") {
    config.allowUnfree = true;
  };
  unstable_pkgs = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/fa35a3c8e17a3de613240fea68f876e5b4896aec.tar.gz") {};
 
in pkgs.mkShell {
  packages = [
    (pkgs.python312.withPackages (python-pkgs: with python-pkgs; [
      # These packages may fall out of date with those in pyproject.toml
      # See pyproject.toml for the source of truth
      distro
      packaging
      psutil
      pythondialog
      inotify
      requests
      tkinter
    ]))
    pkgs.corefonts
    unstable_pkgs.wineWowPackages.full
  ];
  shellHook = ''
    export WINE_EXE="`which wine`"
    export SKIP_DEPENDENCIES=True
    export WINEBIN_CODE=System
    echo "Run with: python3.12 -m ou_dedetai.main"
  '';
}
