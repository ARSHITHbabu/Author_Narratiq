# OCR browser test fixture

`printed-note.png` is used by `tests/browser/ocr-to-editor.spec.ts` (Stage 12.1, Gate 2; checklist task 3.10's
upload → extract → editor journey). It is a 1400×320 white image with two lines of **printed** text, DejaVu
Sans 56 pt:

> The harbour lamp holds.
> Wren keeps the keys.

It is printed, not handwriting, because the test checks the workflow (upload → GOT-OCR2.0 extraction → text
in the editor). Handwriting recognition quality is a separate, unmeasured question.

Regenerate (Pillow 12.3.0, DejaVu Sans from the Ubuntu `fonts-dejavu-core` package):

```python
from PIL import Image, ImageDraw, ImageFont
img = Image.new("RGB", (1400, 320), "white"); d = ImageDraw.Draw(img)
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 56)
d.text((40, 60), "The harbour lamp holds.", fill="black", font=f)
d.text((40, 170), "Wren keeps the keys.", fill="black", font=f)
img.save("printed-note.png", optimize=True)
```
