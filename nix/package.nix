{
  lib,
  stdenv,
  callPackage,
  makeWrapper,
  python312,
  qt6,
  kdePackages,
  uv2nix,
  pyproject-nix,
  pyproject-build-systems,
}:

let
  python = python312;

  workspace = uv2nix.lib.workspace.loadWorkspace {
    workspaceRoot = ./..;
  };

  uvLockedOverlay = workspace.mkPyprojectOverlay {
    sourcePreference = "wheel";
  };

  hacks = callPackage pyproject-nix.build.hacks { };

  pyprojectOverrides = final: prev: {
    pyqt6 = hacks.nixpkgsPrebuilt {
      from = python.pkgs.pyqt6;
    };
  };

  pythonSet = (callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
    lib.composeManyExtensions [
      pyproject-build-systems.overlays.default
      uvLockedOverlay
      pyprojectOverrides
    ]
  );

  projectNameInToml = "desktop-reminder-system";
  thisProjectAsNixPkg = pythonSet.${projectNameInToml};

  runtimeDeps = workspace.deps.default // {
    pyqt6-sip = [ ];
  };

  appPythonEnv = pythonSet.mkVirtualEnv "${thisProjectAsNixPkg.pname}-env" runtimeDeps;
in
stdenv.mkDerivation {
  pname = thisProjectAsNixPkg.pname;
  version = thisProjectAsNixPkg.version;
  src = ./..;

  nativeBuildInputs = [
    makeWrapper
    qt6.wrapQtAppsHook
  ];

  buildInputs = [
    appPythonEnv
    qt6.qtbase
    qt6.qtwayland
    kdePackages.kwindowsystem
  ];

  installPhase = ''
    mkdir -p $out/bin
    cp run.py $out/bin/${thisProjectAsNixPkg.pname}-script
    chmod +x $out/bin/${thisProjectAsNixPkg.pname}-script
    makeWrapper ${appPythonEnv}/bin/python $out/bin/${thisProjectAsNixPkg.pname} \
      --add-flags $out/bin/${thisProjectAsNixPkg.pname}-script
  '';

  doCheck = false;

  meta = with lib; {
    description = "Desktop reminder system with overlay notifications";
    homepage = "https://github.com/Ishaan-Datta/desktop-reminder-system";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = thisProjectAsNixPkg.pname;
  };
}
