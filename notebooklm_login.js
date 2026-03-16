#!/usr/bin/env node
/**
 * NotebookLM Google Login
 * Logs into Google and saves session cookies for future use.
 * Run once: node notebooklm_login.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const CREDS_PATH = path.join(process.env.HOME, '.openclaw/secrets/notebooklm-google.json');
const SESSION_PATH = path.join(process.env.HOME, '.openclaw/secrets/notebooklm-session.json');

async function login() {
  const { email, password } = JSON.parse(fs.readFileSync(CREDS_PATH));
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  console.log('Navigating to Google login...');
  await page.goto('https://accounts.google.com/signin/v2/identifier', { waitUntil: 'networkidle' });

  // Email
  await page.fill('input[type="email"]', email);
  await page.click('#identifierNext');
  await page.waitForTimeout(2000);

  // Password
  await page.waitForSelector('input[type="password"]', { timeout: 10000 });
  await page.fill('input[type="password"]', password);
  await page.click('#passwordNext');
  await page.waitForTimeout(3000);

  // Check if login succeeded
  const url = page.url();
  console.log('Current URL:', url);

  if (url.includes('myaccount') || url.includes('accounts.google.com/signin/oauth')) {
    console.log('Login may need additional verification. Trying to navigate to NotebookLM...');
  }

  // Navigate to NotebookLM
  await page.goto('https://notebooklm.google.com', { waitUntil: 'networkidle', timeout: 30000 });
  const finalUrl = page.url();
  console.log('NotebookLM URL:', finalUrl);

  if (finalUrl.includes('notebooklm.google.com')) {
    // Save cookies
    const cookies = await context.cookies();
    const storage = await context.storageState();
    fs.writeFileSync(SESSION_PATH, JSON.stringify(storage, null, 2));
    console.log('✅ Session saved to', SESSION_PATH);
    console.log('Cookies count:', cookies.length);
  } else {
    console.log('❌ Login failed or redirected. URL:', finalUrl);
    // Take screenshot for debugging
    await page.screenshot({ path: '/tmp/login-debug.png' });
    console.log('Screenshot saved to /tmp/login-debug.png');
  }

  await browser.close();
}

login().catch(console.error);
