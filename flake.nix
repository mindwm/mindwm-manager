{
  description = "A MindWM-Manager service implemented in Python";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/24.05";
    flake-parts.url = "github:hercules-ci/flake-parts";
    surrealdb-py.url = "github:omgbebebe/surrealdb.py-nix";
    surrealdb-py.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ flake-parts, nixpkgs, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [];
      systems = [ "x86_64-linux" "aarch64-linux" ];
      perSystem = { config, self', inputs', pkgs, system, ... }:
      let
        my_python = pkgs.python3.withPackages (ps: with ps; [
          inputs.surrealdb-py.packages.${system}.default
          nats-py
          python-decouple
          aiofiles
          dbus-next
          pyte
          textfsm tabulate
        ]);
        project = pkgs.callPackage ./package.nix {
          python = my_python;
        };
      in { 
        packages.default = project;
        devShells.default = pkgs.mkShell {
#          packages = [ project ];
          buildInputs = with pkgs; [
            my_python
            natscli
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
