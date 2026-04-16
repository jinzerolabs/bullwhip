# nix/packages.nix — Bull Whip Agent package built with uv2nix
{ inputs, ... }: {
  perSystem = { pkgs, system, ... }:
    let
      hermesVenv = pkgs.callPackage ./python.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
      };

      # Import bundled skills, excluding runtime caches
      bundledSkills = pkgs.lib.cleanSourceWith {
        src = ../skills;
        filter = path: _type:
          !(pkgs.lib.hasInfix "/index-cache/" path);
      };

      runtimeDeps = with pkgs; [
        nodejs_20 ripgrep git openssh ffmpeg tirith
      ];

      runtimePath = pkgs.lib.makeBinPath runtimeDeps;
    in {
      packages.default = pkgs.stdenv.mkDerivation {
        pname = "bullwhip-agent";
        version = (builtins.fromTOML (builtins.readFile ../pyproject.toml)).project.version;

        dontUnpack = true;
        dontBuild = true;
        nativeBuildInputs = [ pkgs.makeWrapper ];

        installPhase = ''
          runHook preInstall

          mkdir -p $out/share/bullwhip-agent $out/bin
          cp -r ${bundledSkills} $out/share/bullwhip-agent/skills

          ${pkgs.lib.concatMapStringsSep "\n" (name: ''
            makeWrapper ${hermesVenv}/bin/${name} $out/bin/${name} \
              --suffix PATH : "${runtimePath}" \
              --set BULLWHIP_BUNDLED_SKILLS $out/share/bullwhip-agent/skills
          '') [ "bullwhip" "bullwhip-agent" "bullwhip-acp" ]}

          runHook postInstall
        '';

        meta = with pkgs.lib; {
          description = "AI agent with advanced tool-calling capabilities";
          homepage = "https://github.com/NousResearch/bullwhip-agent";
          mainProgram = "bullwhip";
          license = licenses.mit;
          platforms = platforms.unix;
        };
      };
    };
}
