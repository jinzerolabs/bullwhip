class HermesAgent < Formula
  include Language::Python::Virtualenv

  desc "Self-improving AI agent that creates skills from experience"
  homepage "https://bullwhip-agent.nousresearch.com"
  # Stable source should point at the semver-named sdist asset attached by
  # scripts/release.py, not the CalVer tag tarball.
  url "https://github.com/NousResearch/bullwhip-agent/releases/download/v2026.3.30/bullwhip_agent-0.6.0.tar.gz"
  sha256 "<replace-with-release-asset-sha256>"
  license "MIT"

  depends_on "certifi" => :no_linkage
  depends_on "cryptography" => :no_linkage
  depends_on "libyaml"
  depends_on "python@3.14"

  pypi_packages ignore_packages: %w[certifi cryptography pydantic]

  # Refresh resource stanzas after bumping the source url/version:
  #   brew update-python-resources --print-only bullwhip-agent

  def install
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resources
    venv.pip_install buildpath

    pkgshare.install "skills", "optional-skills"

    %w[bullwhip bullwhip-agent bullwhip-acp].each do |exe|
      next unless (libexec/"bin"/exe).exist?

      (bin/exe).write_env_script(
        libexec/"bin"/exe,
        BULLWHIP_BUNDLED_SKILLS: pkgshare/"skills",
        BULLWHIP_OPTIONAL_SKILLS: pkgshare/"optional-skills",
        BULLWHIP_MANAGED: "homebrew"
      )
    end
  end

  test do
    assert_match "Bull Whip Agent v#{version}", shell_output("#{bin}/bullwhip version")

    managed = shell_output("#{bin}/bullwhip update 2>&1")
    assert_match "managed by Homebrew", managed
    assert_match "brew upgrade bullwhip-agent", managed
  end
end
