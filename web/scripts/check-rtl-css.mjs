#!/usr/bin/env node
/**
 * Static RTL invariant check over the real stylesheet.
 *
 * jsdom has no layout engine, so a visual RTL assertion would be theatre. This
 * checks the property that actually decides mirroring: every direction-sensitive
 * declaration must use a logical (inline-start/end) form. It runs against the
 * source and against the built bundle, so a stray physical property fails CI.
 */
import { readFile } from 'node:fs/promises'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'

const PHYSICAL = [
  [/(?:^|[;{\s])(margin|padding|border)-(left|right)\s*:/g, 'physical box property'],
  [/text-align\s*:\s*(left|right)/g, 'physical text alignment'],
  [/(?:^|[;{\s])(left|right)\s*:\s*[^;]+;/g, 'physical offset'],
]
const REQUIRED = /margin-inline-start|margin-inline-end|padding-inline-start|padding-inline-end|border-inline-(start|end)|inset-inline-(start|end)/

/**
 * Vite's minifier expands the symmetric `inset: -4px` shorthand into
 * `top/right/bottom/left` with identical values. That is direction-neutral, so a
 * balanced left/right pair carrying the same value is not a defect, however the
 * other declarations are ordered between them. Only those two declarations are
 * dropped for the check; the rest of the block is examined normally, and an
 * unbalanced or value-mismatched pair still fails.
 */
function dropSymmetricOffsets(css) {
  const DECL = /(?:^|[;{])\s*(left|right)\s*:\s*([^;{}]+)/g
  return css.replace(/\{([^{}]*)\}/g, (whole, body) => {
    const values = {}
    for (const match of body.matchAll(DECL)) {
      values[match[1]] = values[match[1]] ?? []
      values[match[1]].push(match[2].trim())
    }
    const left = values.left ?? []
    const right = values.right ?? []
    const symmetric = left.length > 0 && left.length === right.length && left.every((item, index) => item === right[index])
    if (!symmetric) return whole
    const cleaned = body
      .replace(/(^|[;{])\s*left\s*:\s*[^;{}]+/g, '$1')
      .replace(/(^|[;{])\s*right\s*:\s*[^;{}]+/g, '$1')
    return `{${cleaned}}`
  })
}

async function checkFile(path, label) {
  const raw = await readFile(path, 'utf8')
  const css = dropSymmetricOffsets(raw)
  const problems = []
  for (const [pattern, kind] of PHYSICAL) {
    for (const match of css.matchAll(pattern)) {
      const line = css.slice(0, match.index).split('\n').length
      problems.push(`${label}:${line} ${kind}: ${match[0].trim()}`)
    }
  }
  return { css: raw, problems }
}

const target = process.argv[2] ?? 'src/styles.css'
const { css, problems } = await checkFile(target, target)

if (target === 'src/styles.css' && !REQUIRED.test(css)) {
  problems.push('src/styles.css: no logical inline properties found; RTL mirroring cannot work')
}

if (problems.length) {
  console.error('RTL CSS check FAILED')
  for (const problem of problems) console.error('  ' + problem)
  process.exit(1)
}

const logical = (css.match(/inline-(start|end)/g) ?? []).length
console.log(`RTL CSS check passed: ${target} (${css.length} bytes, ${logical} logical inline declarations, 0 physical)`)

if (target === 'src/styles.css') {
  try {
    const assets = join('dist', 'assets')
    const bundle = readdirSync(assets).find((name) => name.endsWith('.css'))
    if (bundle) {
      const built = await checkFile(join(assets, bundle), `dist/assets/${bundle}`)
      if (built.problems.length) {
        console.error('Built bundle still contains physical properties:')
        for (const problem of built.problems) console.error('  ' + problem)
        process.exit(1)
      }
      console.log(`Built bundle check passed: dist/assets/${bundle}`)
    }
  } catch {
    // No build yet: the source check already ran.
  }
}
