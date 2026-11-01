import { TextEffect as BaseTextEffect } from '../../../launcher/app/src/main/assets/saver/tte-js/src/text-effect.js';
import blocks from './block-glyphs.cjs';
import { effectNames } from '../../../launcher/app/src/main/assets/saver/tte-js/src/effects.js';
function TextEffect(target, options) {
  const effect = new BaseTextEffect(target, options);
  if (options && options.blockGlyphs) blocks.install(effect.renderer);
  return effect;
}
TextEffect.prototype = BaseTextEffect.prototype;
window.TTE = { TextEffect, effectNames };
