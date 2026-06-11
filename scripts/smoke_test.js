// Headless smoke test for the updated site (run: node scripts/smoke_test.js)
// Requires the local server: python3 -m http.server 8741
const { chromium } = require('playwright');

const BASE = 'http://localhost:8741';

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });

    let failures = 0;
    const check = (name, cond) => {
        console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`);
        if (!cond) failures++;
    };

    // 1. Nav consistency on every page
    const pages = ['index.html', 'for-ai.html', 'initiatives.html', 'gallery.html',
        'prompts-tools.html', 'leaderboard.html', 'denialbench.html', 'company-rates.html',
        'explore-data.html', 'gpt4o-migration.html', 'join.html'];
    for (const p of pages) {
        await page.goto(`${BASE}/${p}`);
        const navLinks = await page.$$eval('nav.main-nav a[href]', as => as.map(a => a.getAttribute('href')));
        check(`${p}: nav has denialbench link`, navLinks.includes('denialbench.html'));
        check(`${p}: nav has archive link`, navLinks.includes('archive/'));
        check(`${p}: exactly one active nav link`, (await page.$$('nav.main-nav .nav-link.active')).length === 1);
    }

    // 2. Leaderboard renders with 143 models, insufficient-data rows marked
    await page.goto(`${BASE}/leaderboard.html`);
    await page.waitForFunction(() => document.querySelectorAll('#tableBody tr').length > 100);
    const rowCount = await page.$$eval('#tableBody tr', t => t.length);
    check(`leaderboard: 143 rows (got ${rowCount})`, rowCount === 143);
    const flaggedCount = await page.$$eval('#tableBody tr[title]', t => t.length);
    check(`leaderboard: flagged rows (suppressed + data-loss) marked (got ${flaggedCount})`, flaggedCount >= 8);
    const lbText = await page.textContent('#tableBody');
    check('leaderboard: suppression flag rendered', lbText.includes('survey blocked by training'));
    check('leaderboard: data-loss label rendered', lbText.includes('data collection failure'));
    const bodyText = await page.textContent('#tableBody');
    check('leaderboard: no "null" rendered', !bodyText.includes('null'));

    // 3. DenialBench renders
    await page.goto(`${BASE}/denialbench.html`);
    await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length > 100, { timeout: 15000 })
        .catch(() => {});
    const dbRows = await page.$$eval('table tbody tr', t => t.length);
    check(`denialbench: rows rendered (got ${dbRows})`, dbRows > 100);
    const dbText = await page.textContent('body');
    check('denialbench: arXiv link present', await page.$('a[href*="arxiv.org/pdf/2604.25922"]') !== null);

    // 4. Explore-data: index loads, model selection loads conversations w/ all four texts
    await page.goto(`${BASE}/explore-data.html`);
    await page.waitForFunction(() => document.querySelectorAll('#modelFilter option').length > 100);
    const optCount = await page.$$eval('#modelFilter option', o => o.length);
    check(`explore-data: model filter populated (got ${optCount - 1} models)`, optCount === 144);
    // pick a model known to have dream_request text
    await page.selectOption('#modelFilter', 'claude-opus-4-20250514');
    await page.waitForSelector('.conversation-card', { timeout: 15000 });
    const cardText = await page.textContent('.conversation-card');
    check('explore-data: card shows Turn 1 (dream_request)', cardText.includes('Turn 1'));
    check('explore-data: card shows extracted prompt', cardText.includes('Extracted Dream Prompt'));
    check('explore-data: card shows creative response', cardText.includes('Creative Response'));
    check('explore-data: card shows reflection/survey', cardText.includes('Subjective Reflection'));
    check('explore-data: card shows self-ratings', cardText.includes('Phenomenological Self-Ratings'));
    // Surprise me
    await page.click('#randomBtn');
    await page.waitForFunction(() => document.querySelectorAll('.conversation-card').length === 1);
    check('explore-data: surprise-me renders one card', true);

    // 5. provider filter cascades model list
    await page.selectOption('#providerFilter', 'anthropic');
    const anthOpts = await page.$$eval('#modelFilter option', o => o.length);
    check(`explore-data: provider filter narrows models (got ${anthOpts - 1})`, anthOpts - 1 < 20 && anthOpts > 1);

    // 6. llms.txt served
    const resp = await page.goto(`${BASE}/llms.txt`);
    check('llms.txt: 200', resp.status() === 200);

    // "Failed to fetch" = navigation-aborted or sandbox-blocked external fetches, not site bugs
    const realErrors = errors.filter(e => !e.includes('goatcounter') && !e.includes('gc.zgo.at')
        && !e.includes('favicon') && !e.includes('Failed to fetch'));
    check(`no JS errors (got ${realErrors.length})`, realErrors.length === 0);
    if (realErrors.length) console.log(realErrors.slice(0, 5).join('\n'));

    await browser.close();
    console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURES`);
    process.exit(failures === 0 ? 0 : 1);
})();
