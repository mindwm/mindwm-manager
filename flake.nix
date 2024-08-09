{
  description = "A MindWM-Manager service implemented in Python";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/24.05";
    flake-parts.url = "github:hercules-ci/flake-parts";
    surrealdb-py.url = "github:omgbebebe/surrealdb.py-nix";
    surrealdb-py.inputs.nixpkgs.follows = "nixpkgs";
    mindwm-sdk-python.url = "path:/home/pion/work/dev/mindwm/mindwm-sdk-python-ng";
    #mindwm-sdk-python.url = "github:omgbebebe/mindwm-sdk-python-ng";
    mindwm-sdk-python.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ flake-parts, nixpkgs, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [];
      systems = [ "x86_64-linux" "aarch64-linux" ];
      perSystem = { config, self', inputs', pkgs, system, ... }:
      let
        my_python = pkgs.python3.withPackages (ps: with ps; [
          inputs.surrealdb-py.packages.${system}.default
          inputs.mindwm-sdk-python.packages.${system}.default
          nats-py
          python-decouple
          aiofiles
          dbus-next
          pyte
          textfsm tabulate
          pydantic dateutil urllib3
        ]);
        project = pkgs.callPackage ./package.nix {
          python = my_python;
        };
        dockerImage = pkgs.dockerTools.buildImage {
          name = "mindwm-manager";
          config = {
            cmd = [ "${project}/bin/mindwm-manager" ];
          };
        };
      in {
        packages.default = project;
        packages.docker = dockerImage;
        devShells.default = pkgs.mkShell {
          packages = [ my_python ];
          buildInputs = with pkgs; [
            natscli
            tmuxp
          ];
          shellHook = ''
            export PYTHONPATH="$PYTHONPATH:./src"
          '';
        };
      };
      flake = {
      };
    };
}
