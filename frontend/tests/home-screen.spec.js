import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Tasks as an iPhone Home Screen web app: public/ is copied into the build as-is and served from
// the site root by the SPA fallback. iOS reads apple-touch-icon for the icon and the manifest for
// name, start URL, scope and standalone display.
const frontend = path.resolve(import.meta.dirname, '..')
const publicDir = path.join(frontend, 'public')

function pngSize(file) {
  const buf = readFileSync(file)
  expect(buf.subarray(1, 4).toString('ascii')).toBe('PNG')
  return [buf.readUInt32BE(16), buf.readUInt32BE(20)]
}

describe('home screen web app', () => {
  const manifest = JSON.parse(readFileSync(path.join(publicDir, 'manifest.webmanifest'), 'utf8'))
  const indexHtml = readFileSync(path.join(frontend, 'index.html'), 'utf8')

  it('opens standalone, scoped to the whole site', () => {
    expect(manifest.name).toBe('Tasks')
    expect(manifest.display).toBe('standalone')
    expect(manifest.start_url).toBe('/')
    expect(manifest.scope).toBe('/')
  })

  it('lists icons that exist at the sizes they claim', () => {
    for (const icon of manifest.icons) {
      const file = path.join(publicDir, icon.src)
      expect(existsSync(file), icon.src).toBe(true)
      expect(pngSize(file).join('x')).toBe(icon.sizes)
    }
  })

  it('links the manifest, the favicon and an opaque 180px apple-touch-icon', () => {
    expect(indexHtml).toContain('<link rel="manifest" href="/manifest.webmanifest" />')
    expect(indexHtml).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
    expect(existsSync(path.join(publicDir, 'favicon.svg'))).toBe(true)
    const touchIcon = path.join(publicDir, 'apple-touch-icon.png')
    expect(pngSize(touchIcon)).toEqual([180, 180])
    // PNG colour type 2 (RGB, no alpha): iOS paints transparent pixels black.
    expect(readFileSync(touchIcon)[25]).toBe(2)
  })
})
