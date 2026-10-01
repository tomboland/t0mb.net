# Build and publish

Build on your development machine, then push the public files to the separate
release repository:

```sh
bash deploy.sh
```

Commit source edits first. The command builds the Hakyll executable using Cabal's
persistent cache, rebuilds the static output (so deleted pages disappear), and
copies `_site/` into `~/repos/t0mb.net-release/site/`. It writes `release.json`
with the source commit and SHA-256 hashes, commits changes, and pushes `main`.
No TMDB access is needed to build the site.

Options:

- `--repo PATH`: use another local release checkout.
- `--no-push`: build and commit locally, without publishing.
- `--allow-dirty`: explicitly allow uncommitted source edits, recorded in the manifest.

The release checkout must be clean and on `main`. To prepare a new build machine,
clone the source, install its Python/Haskell dependencies plus Git and rsync,
and clone the release repository:

```sh
git clone ssh://git@pigeon.t0mb.net:2222/srv/git/t0mb.net-release.git ~/repos/t0mb.net-release
git -C ~/repos/t0mb.net-release config core.sshCommand 'ssh -o ClearAllForwardings=yes'
```

# Server deployment

The Ansible repository's `playbooks/web-release.yml` configures read-only release
access and migrates pigeon and harrier. It does not run the mail, DNS, certificate,
or nginx configuration roles. The existing deploy SSH keys must be available.

Each server's existing five-minute user timer runs
`/home/deploy/.local/bin/t0mb-net-deploy`. It pulls the release checkout, verifies
all published file hashes, copies a new release into
`/var/www/t0mb.net/releases/<release-commit>`, and atomically switches `public`
to that directory. `previous` points to the preceding release. Nothing compiles
on either server. A failed validation leaves the live release unchanged.

The initial migration preserves the former `public` directory as a `legacy-*`
release; converting that directory to a symlink has a brief one-time gap.
Subsequent switches are atomic. Old release directories are retained; remove
unneeded ones manually after checking the `public` and `previous` targets.

The old source checkout is retained, but its post-merge deployment hook is renamed
with a `.disabled` suffix. Deployment scripts live outside Git checkouts.
The canonical deployer is `scripts/deploy-release.py`; when changing it, also
update `roles/t0mb_web_site/files/deploy-release.py` in the Ansible repository.

As `deploy`, first set these if your session lacks the user systemd environment:

```sh
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user start t0mb_net-pull-deploy.service
journalctl --user -u t0mb_net-pull-deploy.service -n 30
```

To roll back, stop the timer and any running deployment, then switch to the
previous release (as `deploy`):

```sh
systemctl --user stop t0mb_net-pull-deploy.timer t0mb_net-pull-deploy.service
cd /var/www/t0mb.net
ln -s "$(readlink previous)" .public-rollback
mv -Tf .public-rollback public
```

Leave the timer stopped until a corrected release is pushed; restarting it
otherwise reapplies the latest release. Retaining old directories is for rollback,
not a substitute for backing up the Git repositories.
