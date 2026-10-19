// The two behaviours react-router 7 will make standard, switched on now in version 6 (the library's own upgrade path), so the later move to 7 changes
// nothing visible and the console warnings go away. Every link and redirect in this application uses an absolute path and there is no splat route,
// so neither change alters where anything leads. Used by main.tsx and by the tests that mount a router.
export const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true } as const
