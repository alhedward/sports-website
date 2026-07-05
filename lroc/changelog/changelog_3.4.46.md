# v3.4.46 — Advert Artwork Size / Caption Repair

- Built from the clean TinyMCE A4 composer baseline.
- Treats generated advert assets as advert artwork even if older article HTML missed the inline-advert marker.
- Suppresses captions for generated advert artwork and Insert Advert artwork.
- Preserves deliberate TinyMCE advert resize by carrying the resized display width into A4 preview and Issue Builder render paths.
- Keeps advert artwork borderless/no-surround while leaving normal article image borders untouched.
