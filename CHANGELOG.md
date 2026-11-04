# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For visual categorization of changes emojis are used in accordance with [gitmoji](https://gitmoji.dev).

## [2.7.0] - 2026-11-04

### ✨ Added
- Compatibility with `melon>=1.0.0-rc.7`.
- **ID_Checker** and **Slugger** extensions now can work with ranobe.

### 🎨 Changed
- Main parser logic separated into core for using in childrens.

## [2.6.0] - 2026-10-23

### ✨ Added
- ExManga extension for receiving slides from [ExManga](https://exmanga.org).
- Slugger extension for scanning slides on images servers by URL.
- New Melon settings model supporting.
- Custom option `only_best_cover` for only one cover downloading.

### 🎨 Changed
- Authorization now managed by Melon subsystem.
- Use `TitleDescriptor` provided by Melon.
- Default catalog sorted now with `-score` instead `-chapter_date`.

### 🐛 Fixed
- Max catalog page can be exceeded.
- Collectiong progress missing in terminal.
- Image server [img3.reimg2.org](https://img3.reimg2.org) accessible only if no token and from CIS countries.
