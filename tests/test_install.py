"""install.sh against a throwaway CLAUDE_CONFIG_DIR. It must never write through a link."""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "drover")


class InstallLinks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.dest = os.path.join(self.tmp, "config", "skills", "drover")
        os.makedirs(os.path.dirname(self.dest))

    def install(self):
        env = {"CLAUDE_CONFIG_DIR": os.path.join(self.tmp, "config"), "PATH": "/usr/bin:/bin", "HOME": self.tmp}
        return subprocess.run(["sh", os.path.join(ROOT, "install.sh")], env=env, capture_output=True, text=True)

    def test_plain_install_copies_both_files(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.access(os.path.join(self.dest, "drover"), os.X_OK))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "SKILL.md")))

    def test_link_to_this_checkout_is_left_alone(self):
        os.symlink(SKILL, self.dest)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already points at this checkout", r.stdout)

    def test_link_to_another_checkout_is_refused_and_not_written_through(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        body = "---\nname: drover\n---\nanother checkout\n"
        with open(os.path.join(other, "SKILL.md"), "w") as f:
            f.write(body)
        os.symlink(other, self.dest)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("link", r.stderr)
        with open(os.path.join(other, "SKILL.md")) as f:
            self.assertEqual(f.read(), body)
        self.assertFalse(os.path.exists(os.path.join(other, "drover")))

    def test_broken_link_is_refused(self):
        os.symlink(os.path.join(self.tmp, "missing"), self.dest)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("link", r.stderr)


if __name__ == "__main__":
    unittest.main()
