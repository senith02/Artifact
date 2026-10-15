# Render every Mermaid source in this folder to ../<name>.png (3x scale, white) and ../<name>.svg.
# Needs Node.js and @mermaid-js/mermaid-cli; pass the mmdc path and a Puppeteer config if Chromium
# is not bundled, e.g.:
#   .\render_diagrams.ps1 -Mmdc C:\tools\mmd\node_modules\.bin\mmdc.cmd -Puppeteer C:\tools\mmd\pp.json
param(
    [string]$Mmdc = "mmdc",
    [string]$Puppeteer = ""
)
$src = $PSScriptRoot
$out = Split-Path $src -Parent
$cfg = Join-Path $src "mermaid-config.json"
foreach ($f in Get-ChildItem $src -Filter *.mmd) {
    foreach ($ext in @("png", "svg")) {
        $target = Join-Path $out ($f.BaseName + "." + $ext)
        $args = @("-i", $f.FullName, "-o", $target, "-c", $cfg, "-b", "white", "-q")
        if ($ext -eq "png") { $args += @("-s", "3") }
        if ($Puppeteer) { $args += @("-p", $Puppeteer) }
        & $Mmdc @args
        if ($LASTEXITCODE -ne 0) { Write-Error "failed: $($f.Name) -> $ext"; exit 1 }
    }
    Write-Output "rendered $($f.BaseName)"
}
