{
  description = "Desktop Reminder System - KDE Plasma overlay notifications";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

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
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Load the uv workspace from the current directory
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Create package overlay from workspace
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      # Python version to use
      pythonVersion = "python312";

      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

      # Build the Python environment for each system
      mkPythonEnv =
        system:
        let
          pkgs = pkgsFor system;
          python = pkgs.${pythonVersion};

          # Extend pyproject-nix with build systems
          pyprojectOverrides = pyproject-build-systems.overlays.default;

          # Create the Python package set
          pythonSet =
            (pkgs.callPackage pyproject-nix.build.packages {
              inherit python;
            }).overrideScope
              (
                nixpkgs.lib.composeManyExtensions [
                  pyprojectOverrides
                  overlay
                  # Custom overrides for PyQt6 and other system deps
                  (final: prev: {
                    # PyQt6 needs special handling - use system package
                    pyqt6 = prev.pyqt6.overrideAttrs (old: {
                      # Use nixpkgs PyQt6 bindings
                      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [
                        pkgs.qt6.wrapQtAppsHook
                      ];
                      buildInputs = (old.buildInputs or [ ]) ++ [
                        pkgs.qt6.qtbase
                        pkgs.qt6.qtwayland
                      ];
                    });
                  })
                ]
              );
        in
        pythonSet;

    in
    {
      # Development shells
      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          python = pkgs.${pythonVersion};
        in
        {
          default = pkgs.mkShell {
            packages = [
              python
              pkgs.uv
              pkgs.qt6.qtbase
              pkgs.qt6.qtwayland
              pkgs.libxkbcommon
            ];

            shellHook = ''
              echo "Desktop Reminder System development shell"
              echo "Run 'uv sync' to install dependencies"
              echo "Run 'uv run python run.py' to start the app"
              echo "Run 'uv run python -m tests.manual_trigger' to test overlay"

              # Qt6 setup for Wayland/X11
              export QT_QPA_PLATFORM="xcb;wayland"
              export QT_PLUGIN_PATH="${pkgs.qt6.qtbase}/${pkgs.qt6.qtbase.qtPluginPrefix}"
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

      # Packages
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          python = pkgs.${pythonVersion};
        in
        {
          default = self.packages.${system}.reminder-system;

          # Main application package using standard nixpkgs Python
          reminder-system = pkgs.python3Packages.buildPythonApplication {
            pname = "desktop-reminder-system";
            version = "1.0.0";
            format = "pyproject";

            src = ./.;

            nativeBuildInputs = [
              pkgs.python3Packages.setuptools
              pkgs.python3Packages.wheel
              pkgs.qt6.wrapQtAppsHook
            ];

            buildInputs = [
              pkgs.qt6.qtbase
              pkgs.qt6.qtwayland
            ];

            propagatedBuildInputs = [
              pkgs.python3Packages.pyqt6
              pkgs.python3Packages.croniter
            ]
            ++ pkgs.lib.optionals (pkgs.python3.pythonOlder "3.11") [
              pkgs.python3Packages.tomli
            ];

            # Don't run tests during build
            doCheck = false;

            # Ensure Qt plugins are found
            dontWrapQtApps = true;

            postFixup = ''
              wrapQtApp $out/bin/reminder-system
            '';

            meta = with pkgs.lib; {
              description = "Desktop reminder system with overlay notifications";
              homepage = "https://github.com/yourusername/desktop-reminder-system";
              license = licenses.mit;
              platforms = platforms.linux;
            };
          };
        }
      );

      # NixOS module for system integration
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        with lib;
        let
          cfg = config.services.reminder-system;
        in
        {
          options.services.reminder-system = {
            enable = mkEnableOption "Desktop Reminder System";

            configFile = mkOption {
              type = types.nullOr types.path;
              default = null;
              description = "Path to the configuration file";
            };
          };

          config = mkIf cfg.enable {
            environment.systemPackages = [ self.packages.${pkgs.system}.default ];

            # User service would be set up via home-manager typically
          };
        };

      # Home-manager module
      homeManagerModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        with lib;
        let
          cfg = config.services.reminder-system;
        in
        {
          options.services.reminder-system = {
            enable = mkEnableOption "Desktop Reminder System";

            package = mkOption {
              type = types.package;
              default = self.packages.${pkgs.system}.default;
              description = "The reminder-system package to use";
            };

            settings = mkOption {
              type = types.attrsOf (
                types.submodule {
                  options = {
                    schedule = mkOption {
                      type = types.str;
                      description = "Cron expression for the reminder";
                    };
                    icon = mkOption {
                      type = types.str;
                      description = "Icon filename (PNG)";
                    };
                    snooze_duration = mkOption {
                      type = types.int;
                      default = 300;
                      description = "Snooze duration in seconds";
                    };
                  };
                }
              );
              default = { };
              description = "Reminder configurations";
            };
          };

          config = mkIf cfg.enable {
            home.packages = [ cfg.package ];

            # Generate config file
            xdg.configFile."reminder-system/config.toml".text =
              let
                toToml = name: value: ''
                  [${name}]
                  schedule = "${value.schedule}"
                  icon = "${value.icon}"
                  snooze_duration = ${toString value.snooze_duration}
                '';
              in
              concatStringsSep "\n" (mapAttrsToList toToml cfg.settings);

            # Systemd user service
            systemd.user.services.reminder-system = {
              Unit = {
                Description = "Desktop Reminder System";
                After = [ "graphical-session.target" ];
                PartOf = [ "graphical-session.target" ];
              };

              Service = {
                ExecStart = "${cfg.package}/bin/reminder-system";
                Restart = "on-failure";
                RestartSec = 5;
              };

              Install = {
                WantedBy = [ "graphical-session.target" ];
              };
            };
          };
        };
    };
}
