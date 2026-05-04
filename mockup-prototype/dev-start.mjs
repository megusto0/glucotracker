/**
 * dev-start.mjs — drop-in replacement for "vite --open"
 *
 * If port 5199 is occupied by a dead/stale process, kills it first so Vite
 * (with strictPort: true) doesn't fail. On a clean machine the kill step is
 * a silent no-op.
 */
import { execFileSync, spawn } from 'node:child_process'

const PORT = 5199

// Attempt to free the port on Windows via PowerShell.
// Silently ignored if nothing is listening or if PowerShell is unavailable.
try {
  execFileSync(
    'powershell.exe',
    [
      '-NonInteractive',
      '-Command',
      `$pids = (Get-NetTCPConnection -LocalPort ${PORT} -State Listen -ErrorAction SilentlyContinue).OwningProcess;` +
      `foreach ($p in $pids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }`,
    ],
    { stdio: 'ignore' },
  )
} catch {
  // PowerShell unavailable or other error — proceed anyway
}

// Brief pause so the OS releases the port before Vite binds it
await new Promise(r => setTimeout(r, 350))

// Start Vite without auto-opening a browser tab (the preview tool handles that)
const vite = spawn('npx', ['vite', '--no-open'], {
  stdio: 'inherit',
  shell: true,
})

vite.on('exit', code => process.exit(code ?? 0))
