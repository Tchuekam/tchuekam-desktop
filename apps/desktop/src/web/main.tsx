/**
 * Entry point for the hosted web build (index.web.html).
 *
 * The shared renderer reads `window.hermesDesktop` as soon as it boots, so the
 * browser bridge has to exist before any of it loads. That ordering is what
 * the dynamic import buys: a static `import '../main'` would be hoisted above
 * the install call and the app would come up with no bridge.
 */
import { installWebBridge } from './bridge'

installWebBridge()

void import('../main')
