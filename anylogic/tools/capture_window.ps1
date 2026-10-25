<#
.SYNOPSIS
  Capture PNG frames of the AnyLogic run window (Chromium --app window) without a GUI driver.

.DESCRIPTION
  AnyLogic 8.9 PLE shows a running model in its own bundled Chromium:
    chrome.exe --app=http://localhost:<port> --test-type --user-data-dir=...\.AnyLogicPLE\...\chromium\userData
  This script finds that window (by process command line, optional title text, or an explicit HWND),
  and grabs N frames, one every IntervalMs, as PNG files. Default method is PrintWindow with
  PW_RENDERFULLCONTENT (works while other windows cover it). If the frame comes back black
  (GPU/WebGL content such as the 3D window can do that) use -Mode Screen, which copies the screen
  rectangle instead (the window must then be visible and not covered).

  It never starts, stops or touches AnyLogic. Read-only apart from the PNG files it writes.

.EXAMPLE
  # list candidate windows, nothing is captured
  powershell -ExecutionPolicy Bypass -File capture_window.ps1 -List

  # 60 frames, 8 per second, client area only, into results\animation\raw
  powershell -ExecutionPolicy Bypass -File capture_window.ps1 -OutDir results\animation\raw -Count 60 -IntervalMs 125 -ClientOnly

  # same, but for a 3D window that PrintWindow renders black
  powershell -ExecutionPolicy Bypass -File capture_window.ps1 -OutDir results\animation\raw -Count 60 -IntervalMs 125 -ClientOnly -Mode Screen
#>
param(
  [string]$OutDir = ".\frames",
  [string]$Title = "",
  [string]$CmdLike = "--app=http://localhost",
  [string]$ProcessName = "chrome.exe",
  [long]$Handle = 0,
  [int]$Count = 1,
  [int]$IntervalMs = 125,
  [string]$Prefix = "frame",
  [ValidateSet("PrintWindow", "Screen")][string]$Mode = "PrintWindow",
  [switch]$ClientOnly,
  [switch]$Restore,
  [switch]$List,
  [int]$X = 0, [int]$Y = 0, [int]$W = 0, [int]$H = 0
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Cw {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int command);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  public class Win { public long Handle; public uint Pid; public string Title; public int Width; public int Height; }
  public static List<Win> Top() {
    var list = new List<Win>();
    EnumWindows((h, p) => {
      if (!IsWindowVisible(h)) return true;
      int n = GetWindowTextLength(h);
      var sb = new StringBuilder(n + 2);
      GetWindowText(h, sb, sb.Capacity);
      uint pid; GetWindowThreadProcessId(h, out pid);
      RECT r; GetWindowRect(h, out r);
      list.Add(new Win { Handle = h.ToInt64(), Pid = pid, Title = sb.ToString(), Width = r.R - r.L, Height = r.B - r.T });
      return true;
    }, IntPtr.Zero);
    return list;
  }
}
"@
[Cw]::SetProcessDPIAware() | Out-Null

function Find-Window {
  if ($Handle -ne 0) { return [IntPtr]$Handle }
  $pids = @{}
  Get-CimInstance Win32_Process -Filter "Name='$ProcessName'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$CmdLike*" } |
    ForEach-Object { $pids[[uint32]$_.ProcessId] = $_.CommandLine }
  if ($Restore -and $Title) {
    [Cw]::Top() | Where-Object { $pids.ContainsKey($_.Pid) -and $_.Title -like "*$Title*" } |
      ForEach-Object { [Cw]::ShowWindow([IntPtr]$_.Handle,9) | Out-Null }
    Start-Sleep -Milliseconds 300
  }
  $c = [Cw]::Top() | Where-Object { $pids.ContainsKey($_.Pid) -and $_.Width -gt 200 -and $_.Height -gt 150 }
  if ($Title) { $c = $c | Where-Object { $_.Title -like "*$Title*" } }
  if ($List) {
    $c | ForEach-Object { Write-Host ("{0}`tpid={1}`t{2}x{3}`t{4}" -f $_.Handle, $_.Pid, $_.Width, $_.Height, $_.Title) }
    return $null
  }
  $w = $c | Sort-Object { $_.Width * $_.Height } -Descending | Select-Object -First 1
  if (-not $w) { throw "No visible window found (ProcessName=$ProcessName, CmdLike='$CmdLike', Title='$Title'). Run with -List." }
  return [IntPtr]$w.Handle
}

function Test-Black([System.Drawing.Bitmap]$b) {
  $sum = 0; $n = 0
  for ($i = 1; $i -le 20; $i++) { for ($j = 1; $j -le 20; $j++) {
    $c = $b.GetPixel([int]($b.Width * $i / 21), [int]($b.Height * $j / 21)); $sum += $c.R + $c.G + $c.B; $n++ } }
  return (($sum / ($n * 3)) -lt 3)
}

function Grab([IntPtr]$hwnd) {
  $r = New-Object Cw+RECT; [Cw]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $ww = $r.R - $r.L; $wh = $r.B - $r.T
  # offset of client area inside the window bitmap
  $cr = New-Object Cw+RECT; [Cw]::GetClientRect($hwnd, [ref]$cr) | Out-Null
  $pt = New-Object Cw+POINT; [Cw]::ClientToScreen($hwnd, [ref]$pt) | Out-Null
  $offX = $pt.X - $r.L; $offY = $pt.Y - $r.T
  $cw = $cr.R; $ch = $cr.B
  if ($Mode -eq "PrintWindow") {
    $bmp = New-Object System.Drawing.Bitmap $ww, $wh
    $g = [System.Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    [Cw]::PrintWindow($hwnd, $hdc, 2) | Out-Null          # 2 = PW_RENDERFULLCONTENT
    $g.ReleaseHdc($hdc); $g.Dispose()
  } else {
    $bmp = New-Object System.Drawing.Bitmap $ww, $wh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $ww, $wh))
    $g.Dispose()
  }
  if ($ClientOnly) { $rect = New-Object System.Drawing.Rectangle $offX, $offY, $cw, $ch }
  else { $rect = New-Object System.Drawing.Rectangle 0, 0, $ww, $wh }
  if ($W -gt 0 -and $H -gt 0) { $rect = New-Object System.Drawing.Rectangle ($rect.X + $X), ($rect.Y + $Y), $W, $H }
  $crop = $bmp.Clone($rect, $bmp.PixelFormat); $bmp.Dispose()
  return $crop
}

$hwnd = Find-Window
if ($List) { return }
if ([Cw]::IsIconic($hwnd)) {
  if ($Restore) { [Cw]::ShowWindow($hwnd,9) | Out-Null; Start-Sleep -Milliseconds 300 }
  else { throw "Window is minimised; PrintWindow returns nothing. Restore it first." }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$sw = [Diagnostics.Stopwatch]::StartNew()
$blackSeen = 0
for ($k = 1; $k -le $Count; $k++) {
  $t0 = $sw.ElapsedMilliseconds
  $img = Grab $hwnd
  if (Test-Black $img) { $blackSeen++ }
  $file = Join-Path $OutDir ("{0}-{1:D4}.png" -f $Prefix, $k)
  $img.Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $w0 = $img.Width; $h0 = $img.Height; $img.Dispose()
  $spent = $sw.ElapsedMilliseconds - $t0
  if ($k -lt $Count -and $spent -lt $IntervalMs) { Start-Sleep -Milliseconds ($IntervalMs - $spent) }
}
"saved $Count frame(s) {0}x{1} to $OutDir (mode=$Mode, hwnd=$hwnd, avg {2} ms/frame)" -f $w0, $h0, [int]($sw.ElapsedMilliseconds / $Count)
if ($blackSeen -gt 0) { Write-Warning "$blackSeen of $Count frames look black: retry with -Mode Screen (window must be uncovered)." }
