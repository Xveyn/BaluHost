#!/usr/bin/env node
/**
 * Generate BaluDesk app icons from SVG
 * Requires: npm install -g sharp
 */

const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const svgContent = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <!-- Background -->
  <rect width="256" height="256" fill="#0f172a"/>
  
  <!-- Outer glow circle -->
  <circle cx="128" cy="128" r="115" fill="none" stroke="#0ea5e9" stroke-width="2" opacity="0.3"/>
  
  <!-- Main cloud shape with gradient effect -->
  <defs>
    <radialGradient id="cloudGradient" cx="50%" cy="40%">
      <stop offset="0%" style="stop-color:#06b6d4;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0ea5e9;stop-opacity:1" />
    </radialGradient>
  </defs>
  
  <!-- Cloud -->
  <g transform="translate(128, 128)">
    <path d="M -35 -5 Q -45 -25 -25 -45 Q -5 -55 15 -45 Q 35 -25 25 0 L 35 0 Q 50 -15 50 5 Q 50 25 35 35 L -40 35 Q -55 25 -55 5 Q -55 -15 -35 -5 Z" 
          fill="url(#cloudGradient)" stroke="#06b6d4" stroke-width="1.5"/>
  </g>
  
  <!-- Sync arrows inside cloud -->
  <g transform="translate(128, 125)" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <!-- Right arrow -->
    <path d="M 5 -15 L 25 -15 M 20 -20 L 25 -15 L 20 -10"/>
    <!-- Left arrow -->
    <path d="M -5 15 L -25 15 M -20 20 L -25 15 L -20 10"/>
  </g>
</svg>
`;

const publicDir = path.join(__dirname, 'public');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir, { recursive: true });
}

// Generate icon.png (256x256)
sharp(Buffer.from(svgContent))
  .png()
  .resize(256, 256, { fit: 'contain', background: { r: 15, g: 23, b: 42, alpha: 1 } })
  .toFile(path.join(publicDir, 'icon.png'))
  .then(() => console.log('✅ Generated icon.png (256x256)'))
  .catch(err => console.error('❌ Error generating icon:', err));

// Generate icon-small.png (32x32) for tray
sharp(Buffer.from(svgContent))
  .png()
  .resize(32, 32, { fit: 'contain', background: { r: 15, g: 23, b: 42, alpha: 1 } })
  .toFile(path.join(publicDir, 'icon-small.png'))
  .then(() => console.log('✅ Generated icon-small.png (32x32)'))
  .catch(err => console.error('❌ Error generating small icon:', err));

// Generate icon-large.png (512x512) for app stores
sharp(Buffer.from(svgContent))
  .png()
  .resize(512, 512, { fit: 'contain', background: { r: 15, g: 23, b: 42, alpha: 1 } })
  .toFile(path.join(publicDir, 'icon-large.png'))
  .then(() => console.log('✅ Generated icon-large.png (512x512)'))
  .catch(err => console.error('❌ Error generating large icon:', err));
