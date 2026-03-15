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
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;

        # 1. Load Project Workspace (parses pyproject.toml, uv.lock)
        workspace = uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = ./.; # Root of the flake/project
        };

        # 2. Generate Nix Overlay from uv.lock (via workspace)
        uvLockedOverlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel"; # Or "sdist"
        };

        # 3. Custom Package Overrides
        hacks = pkgs.callPackage pyproject-nix.build.hacks { };
        # Get the prebuilt packages from nixpkgs
        pyprojectOverrides = final: prev: {
          pyqt6 = hacks.nixpkgsPrebuilt {
            from = python.pkgs.pyqt6;
          };
        };

        # 4. Construct the Final Python Package Set
        pythonSet = (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
          nixpkgs.lib.composeManyExtensions [
            pyproject-build-systems.overlays.default # For build tools
            uvLockedOverlay # Locked dependencies
            pyprojectOverrides # Fixes
          ]
        );

        # Matches name in pyproject.toml
        projectNameInToml = "desktop-reminder-system";
        thisProjectAsNixPkg = pythonSet.${projectNameInToml};

        # Force pyqt6-sip into the virtual env
        runtimeDeps = workspace.deps.default // {
          pyqt6-sip = [ ];
        };

        # 5. Create the Python Runtime Environment
        appPythonEnv = pythonSet.mkVirtualEnv (thisProjectAsNixPkg.pname + "-env") runtimeDeps; # Uses deps from pyproject.toml [project.dependencies]
      in
      {
        # Development Shell
        devShells.default = pkgs.mkShell {
          packages = [
            appPythonEnv
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
            export UV_PYTHON="${python}/bin/python"
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

        # Nix Packaging the Application
        packages.default = pkgs.stdenv.mkDerivation {
          pname = thisProjectAsNixPkg.pname;
          version = thisProjectAsNixPkg.version;
          src = ./.;

          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.qt6.wrapQtAppsHook
          ];

          # Runtime Python environment
          buildInputs = [
            appPythonEnv
            pkgs.qt6.qtbase
            pkgs.qt6.qtwayland
            pkgs.kdePackages.kwindowsystem
          ];

          installPhase = ''
            mkdir -p $out/bin
            cp run.py $out/bin/${thisProjectAsNixPkg.pname}-script
            chmod +x $out/bin/${thisProjectAsNixPkg.pname}-script
            makeWrapper ${appPythonEnv}/bin/python $out/bin/${thisProjectAsNixPkg.pname} \
              --set QT_QPA_PLATFORM xcb \
              --add-flags $out/bin/${thisProjectAsNixPkg.pname}-script
          '';

          # Don't run tests during build
          doCheck = false;

          meta = with pkgs.lib; {
            description = "Desktop reminder system with overlay notifications";
            homepage = "https://github.com/Ishaan-Datta/desktop-reminder-system";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };
        packages.${thisProjectAsNixPkg.pname} = self.packages.${system}.default;

        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/${thisProjectAsNixPkg.pname}";
        };
        apps.${thisProjectAsNixPkg.pname} = self.apps.${system}.default;
      }
    );
}
