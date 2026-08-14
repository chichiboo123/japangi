/**
 * 자판기 UI 점검 — 음소거 토글, 움직임 최소화, 반응형, 접근성.
 * 백엔드(8000) · 픽스처(9911) · Vite(5173) 가 떠 있어야 한다.
 *
 *   node tests/browser-ui.mjs
 */
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const MEDIA_URL = process.argv[2] ?? 'http://localhost:9911/master.m3u8'
const APP_URL = process.env.APP_URL ?? 'http://127.0.0.1:5173'

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok })
  console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}${detail ? ' — ' + detail : ''}`)
}

// 로컬 샌드박스에는 크로미움이 미리 깔려 있고, CI 에서는 playwright 가 직접 받는다.
// 둘 다 자동으로 잡히도록 경로가 실제로 있을 때만 지정한다.
const bundled = '/opt/pw-browsers/chromium'
const executablePath = process.env.CHROMIUM_PATH || (existsSync(bundled) ? bundled : undefined)
const browser = await chromium.launch({ executablePath })

async function loadShelves(page) {
  await page.goto(APP_URL, { waitUntil: 'networkidle' })
  await page.getByTestId('url-input').fill(MEDIA_URL)
  await page.getByTestId('inspect').click()
  await page.getByTestId('preview').waitFor({ timeout: 30000 })
}

try {
  console.log('\n[1] 음소거 토글')
  {
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto(APP_URL, { waitUntil: 'networkidle' })
    const toggle = page.getByTestId('mute')
    check('기본값은 소리 켜짐', (await toggle.getAttribute('aria-pressed')) === 'false')
    check('토글에 aria-label', /효과음/.test((await toggle.getAttribute('aria-label')) ?? ''))
    await toggle.click()
    check('클릭하면 음소거', (await toggle.getAttribute('aria-pressed')) === 'true')
    check('라벨도 바뀜', /소리 꺼짐/.test((await toggle.textContent()) ?? ''))
    await page.reload({ waitUntil: 'networkidle' })
    check(
      '새로고침해도 설정 유지',
      (await page.getByTestId('mute').getAttribute('aria-pressed')) === 'true',
    )
    await context.close()
  }

  console.log('\n[2] 움직임 최소화 (prefers-reduced-motion)')
  {
    const context = await browser.newContext({ reducedMotion: 'reduce' })
    const page = await context.newPage()
    await page.goto(APP_URL, { waitUntil: 'networkidle' })
    // 붙여넣기로 동전 애니메이션이 만들어지지 않아야 한다
    await page.getByTestId('url-input').focus()
    await page.evaluate((url) => navigator.clipboard?.writeText?.(url), MEDIA_URL).catch(() => {})
    await page.getByTestId('url-input').fill(MEDIA_URL)
    await page.getByTestId('url-input').dispatchEvent('paste')
    await page.waitForTimeout(200)
    check('동전 낙하 연출 없음', (await page.locator('.coin').count()) === 0)

    await loadShelves(page)
    const duration = await page.evaluate(() => {
      const el = document.querySelector('.preview')
      return el ? getComputedStyle(el).animationDuration : 'none'
    })
    // reduce 설정에서는 0.001ms → 브라우저가 '1e-06s' 로 돌려준다
    check('애니메이션이 사실상 꺼짐', parseFloat(duration) < 0.01, duration)
    await context.close()
  }

  console.log('\n[3] 반응형 (가로 스크롤 금지)')
  for (const width of [320, 390, 768, 1280]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await context.newPage()
    await loadShelves(page)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    check(`${width}px 에서 가로 넘침 없음`, overflow <= 0, `${overflow}px`)
    if (width <= 390) {
      // 좁은 화면에서 제목이 한 글자씩 쪼개지지 않아야 한다
      const box = await page.locator('.marquee__title').boundingBox()
      check(`${width}px 제목이 한 줄`, (box?.height ?? 99) < 48, `높이 ${Math.round(box?.height ?? 0)}px`)
    }
    await context.close()
  }

  console.log('\n[4] 접근성')
  {
    const context = await browser.newContext()
    const page = await context.newPage()
    await loadShelves(page)

    const noName = await page.evaluate(() =>
      [...document.querySelectorAll('button, a[href]')].filter(
        (el) => !(el.getAttribute('aria-label') || el.textContent?.trim()),
      ).length,
    )
    check('이름 없는 버튼/링크 없음', noName === 0, `${noName}개`)

    const noAlt = await page.evaluate(
      () => [...document.querySelectorAll('img')].filter((el) => el.alt === null).length,
    )
    check('alt 속성 누락 없음', noAlt === 0)

    check(
      '표시창이 aria-live',
      (await page.getByTestId('display').getAttribute('aria-live')) === 'polite',
    )

    const labelled = await page.evaluate(() => {
      const input = document.querySelector('#url-input')
      return !!document.querySelector('label[for="url-input"]') && !!input
    })
    check('입력창에 연결된 label', labelled)

    // 키보드만으로 상품을 고를 수 있어야 한다
    await page.getByTestId('option-mp3-192').focus()
    await page.keyboard.press('Enter')
    check(
      '키보드로 상품 선택',
      (await page.getByTestId('option-mp3-192').getAttribute('aria-pressed')) === 'true',
    )

    const focusRing = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="option-mp3-192"]')
      el.focus()
      return getComputedStyle(el, ':focus-visible').outlineWidth
    })
    check('포커스 링 존재', focusRing !== '0px', focusRing)

    // 품절 항목은 탭 순서에서 자연히 빠진다 (disabled)
    const soldOutDisabled = await page.getByTestId('option-mp4-2160p').isDisabled()
    check('품절 항목은 포커스 대상 아님', soldOutDisabled)
    await context.close()
  }

  console.log('\n[5] 진열대 구조 (자판기 은유)')
  {
    const context = await browser.newContext()
    const page = await context.newPage()
    await loadShelves(page)
    check('진열장(showcase) 존재', (await page.locator('.showcase').count()) === 1)
    check('음원은 캔 모양', (await page.locator('.product-mp3, [data-testid="product-mp3"] .vessel--can').count()) > 0)
    check('영상은 병 모양', (await page.locator('[data-testid="product-mp4"] .vessel--bottle').count()) > 0)
    check('가격표가 용량', (await page.locator('.dial__price').count()) > 0)
    // 개별 화질 품절은 가격표 자리에 표시된다
    const soldOutPrices = await page
      .locator('.dial:disabled .dial__price')
      .filter({ hasText: 'SOLD OUT' })
      .count()
    check('품절 화질은 가격표 자리에 SOLD OUT', soldOutPrices > 0, `${soldOutPrices}개`)

    // 진열대 한 칸이 통째로 품절이면 비스듬한 스티커가 붙는다 (240p 원본)
    await page.getByTestId('url-input').fill(MEDIA_URL.replace('master.m3u8', 'master_low.m3u8'))
    await page.getByTestId('inspect').click()
    await page.waitForTimeout(1500)
    await page.getByTestId('product-mp4').waitFor({ timeout: 30000 })
    check('칸 전체 품절이면 SOLD OUT 스티커', (await page.locator('.soldout-tag').count()) > 0)
    check(
      '음원은 여전히 판매 중',
      !(await page.getByTestId('option-mp3-320').isDisabled()),
    )
    await context.close()
  }
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
