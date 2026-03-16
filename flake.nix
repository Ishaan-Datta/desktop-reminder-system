{
  description = "Desktop Reminder System";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      overlay = final: prev: {
        desktop-reminder-system = final.callPackage ./nix/package.nix {
          inherit uv2nix pyproject-nix pyproject-build-systems;
        };
      };
    in
    {
      overlays.default = overlay;
    }
    // flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
      in
      {
        packages.default = pkgs.desktop-reminder-system;
        packages.desktop-reminder-system = pkgs.desktop-reminder-system;

        apps.default = {
          type = "app";
          program = "${pkgs.desktop-reminder-system}/bin/desktop-reminder-system";
        };
        apps.desktop-reminder-system = self.apps.${system}.default;

        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.python312
            pkgs.ruff
            pkgs.uv
            pkgs.lefthook
            pkgs.qt6.qtbase
            pkgs.qt6.qtwayland
            pkgs.libxkbcommon
          ];

          shellHook = ''
            export QT_QPA_PLATFORM="xcb;wayland"
            export QT_PLUGIN_PATH="${pkgs.qt6.qtbase}/${pkgs.qt6.qtbase.qtPluginPrefix}"
            export UV_PYTHON="${pkgs.python312}/bin/python"
            export UV_PYTHON_DOWNLOADS=never
            unset PYTHONPATH

            lefthook install
            uv sync

            echo "Run 'uv run python run.py' to start the app"
            echo "Run 'uv run python -m tests.manual_trigger' to test overlay"
          '';

          LD_LIBRARY_PATH = nixpkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.qt6.qtbase
            pkgs.libxkbcommon
            pkgs.xorg.libX11
            pkgs.xorg.libXcursor
            pkgs.xorg.libXrandr
            pkgs.xorg.libXi
            pkgs.libGL
            pkgs.fontconfig
            pkgs.freetype
            pkgs.glib
            pkgs.zlib
            pkgs.zstd
            pkgs.dbus
          ];
        };
      }
    );
}
