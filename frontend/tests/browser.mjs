/**
 * 브라우저 e2e — 실제 Chromium 으로 전체 흐름을 돌린다.
 * 백엔드(8000)와 Vite dev 서버(5173)가 떠 있어야 한다.
 *
 *   node tests/browser.mjs "http://localhost:9911/master.m3u8"
 */
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const MEDIA_URL = process.argv[2] ?? 'http://localhost:9911/master.m3u8'
const APP_URL = process.env.APP_URL ?? 'http://127.0.0.1:5173'
const SHOT_DIR = process.env.SHOT_DIR ?? '/tmp/japangi-shots'

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok, detail })
  console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}${detail ? ' — ' + detail : ''}`)
}

// 로컬 샌드박스에는 크로미움이 미리 깔려 있고, CI 에서는 playwright 가 직접 받는다.
// 둘 다 자동으로 잡히도록 경로가 실제로 있을 때만 지정한다.
const bundled = '/opt/pw-browsers/chromium'
const executablePath = process.env.CHROMIUM_PATH || (existsSync(bundled) ? bundled : undefined)
const browser = await chromium.launch({ executablePath })
const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } })
const page = await context.newPage()

// [2] 에서 일부러 잘못된 링크를 넣어 400 을 유발하므로 그것만 제외한다.
let expectBadRequest = false
const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() !== 'error') return
  if (expectBadRequest && /status of 400/.test(msg.text())) return
  consoleErrors.push(msg.text())
})
page.on('pageerror', (err) => consoleErrors.push(String(err)))

try {
  console.log('\n[1] 페이지 로드')
  await page.goto(APP_URL, { waitUntil: 'networkidle' })
  check('제목 렌더링', (await page.title()) === '링크 자판기', await page.title())
  check('초기 표시창', (await page.getByTestId('display').textContent()) === '링크를 넣어주세요')
  check(
    '푸터 링크 정확',
    (await page.locator('footer a').getAttribute('href')) === 'https://litt.ly/chichiboo' &&
      (await page.locator('footer a').textContent())?.trim() === 'Created by. 교육뮤지컬 꿈꾸는 치수쌤',
  )
  check(
    '푸터 target/rel',
    (await page.locator('footer a').getAttribute('target')) === '_blank' &&
      (await page.locator('footer a').getAttribute('rel')) === 'noopener noreferrer',
  )
  check('저작권 안내 노출', (await page.getByText(/수업 목적 이용/).count()) > 0)

  console.log('\n[2] 잘못된 링크')
  expectBadRequest = true
  await page.getByTestId('url-input').fill('https://evil.example.com/video')
  await page.getByTestId('inspect').click()
  await page.getByTestId('error').waitFor({ timeout: 15000 })
  const errorText = await page.getByTestId('error').textContent()
  check('친절한 오류 메시지', /유튜브와 인스타그램/.test(errorText ?? ''), errorText?.slice(0, 60))
  check('스택 트레이스 없음', !/Traceback|yt_dlp|Error:/.test(errorText ?? ''))
  await page.getByTestId('error').getByRole('button').click()
  expectBadRequest = false

  console.log('\n[3] 링크 투입 → 진열대')
  await page.getByTestId('url-input').fill(MEDIA_URL)
  await page.getByTestId('inspect').click()
  await page.getByTestId('preview').waitFor({ timeout: 30000 })
  check('미리보기 표시', (await page.getByTestId('title').textContent())?.length > 0)
  check('MP3 진열', (await page.getByTestId('product-mp3').count()) === 1)
  check('WAV 진열', (await page.getByTestId('product-wav').count()) === 1)
  check('MP4 진열', (await page.getByTestId('product-mp4').count()) === 1)
  check('WebM 진열', (await page.getByTestId('product-webm').count()) === 1)

  const price320 = await page.getByTestId('option-mp3-320').textContent()
  check('가격표(예상 용량) 표시', /약 \d+(\.\d+)? (KB|MB|GB)/.test(price320 ?? ''), price320?.trim())

  const soldOut = page.getByTestId('option-mp4-2160p')
  check('4K SOLD OUT 표시', /SOLD OUT/.test((await soldOut.textContent()) ?? ''))
  check('SOLD OUT 은 클릭 불가', await soldOut.isDisabled())

  const wavBadge = await page.getByTestId('option-wav-48000-24').textContent()
  check('WAV 대용량 라벨', /대용량/.test(wavBadge ?? ''), wavBadge?.trim())

  console.log('\n[4] 접근성')
  const ariaLabel = await page.getByTestId('option-mp3-320').getAttribute('aria-label')
  check('선택지에 aria-label', /MP3 320kbps, 예상 용량/.test(ariaLabel ?? ''), ariaLabel ?? '')
  const soldOutLabel = await soldOut.getAttribute('aria-label')
  check('품절 항목도 이유를 읽어줌', /품절/.test(soldOutLabel ?? ''), soldOutLabel ?? '')
  await page.keyboard.press('Tab')
  const focused = await page.evaluate(() => document.activeElement?.tagName)
  check('키보드 포커스 이동', ['INPUT', 'BUTTON', 'A'].includes(focused ?? ''), focused ?? '')

  console.log('\n[5] 구매 → 진행률 → 배출')
  await page.getByTestId('option-mp3-320').click()

  // 폴링으로는 빠르게 지나가는 단계를 놓친다. MutationObserver 로 모든 렌더를 기록한다.
  await page.evaluate(() => {
    const w = window
    w.__progressLog = { phases: [], percents: [] }
    const sample = () => {
      const node = document.querySelector('[data-testid="progress"]')
      if (!node) return
      const phase = node.querySelector('.dispensing__phase')?.textContent?.trim()
      if (phase && w.__progressLog.phases.at(-1) !== phase) w.__progressLog.phases.push(phase)
      const percent = node.querySelector('[data-testid="percent"]')?.textContent?.trim()
      if (percent) w.__progressLog.percents.push(percent)
    }
    new MutationObserver(sample).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    })
    sample()
  })

  await page.getByTestId('purchase').click()
  await page.getByTestId('tray').waitFor({ timeout: 90000 })

  const log = await page.evaluate(() => window.__progressLog)
  const phases = log.phases
  const percents = [...new Set(log.percents.filter((p) => /^\d+%$/.test(p)))]

  check('다운로드 단계 표시', phases.includes('내려받는 중'), phases.join(' → '))
  check('변환 단계가 따로 표시', phases.includes('변환 중'), phases.join(' → '))
  check('두 단계가 순서대로', phases.indexOf('내려받는 중') < phases.indexOf('변환 중'), phases.join(' → '))
  check('진행률이 실제로 증가', percents.length > 1, `관측된 %: ${percents.join(', ')}`)
  check('배출구 등장', true)

  console.log('\n[6] 파일 저장')
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 20000 }),
    page.getByTestId('save').click(),
  ])
  const suggested = download.suggestedFilename()
  check('파일명 {제목}_{품질}.{확장자}', /_320\.mp3$/.test(suggested), suggested)
  const path = await download.path()
  const { size } = await (await import('node:fs/promises')).stat(path)
  check('파일 내용 존재', size > 10000, `${size.toLocaleString()} bytes`)

  console.log('\n[7] 콘솔 오류')
  check('브라우저 콘솔 에러 없음', consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '))

  await (await import('node:fs/promises')).mkdir(SHOT_DIR, { recursive: true })
  await page.screenshot({ path: `${SHOT_DIR}/flow.png`, fullPage: true })
  console.log(`\n  스크린샷: ${SHOT_DIR}/flow.png`)
} catch (error) {
  check('예외 없이 완주', false, String(error).slice(0, 300))
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log('\n' + '='.repeat(60))
if (failed.length) {
  console.log(`\x1b[31mFAIL\x1b[0m  ${failed.length}개 실패: ${failed.map((f) => f.label).join(', ')}`)
  process.exit(1)
}
console.log(`\x1b[32mPASS\x1b[0m  전체 통과 (${results.length}개)`)
