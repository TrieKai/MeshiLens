(() => {
  function isExtensionContextValid(chromeApi = globalThis.chrome) {
    try {
      return Boolean(chromeApi?.runtime?.id);
    } catch {
      return false;
    }
  }

  function isExtensionContextInvalidatedError(error) {
    const message = String(error?.message || error || "");
    return /extension context invalidated/i.test(message);
  }

  function markInvalidated(error) {
    if (error && typeof error === "object") {
      error.invalidated = true;
      return error;
    }
    const next = new Error(String(error || "Extension context invalidated."));
    next.invalidated = true;
    return next;
  }

  function invalidatedError() {
    return markInvalidated(new Error("Extension context invalidated."));
  }

  /**
   * Wrap chrome.runtime.sendMessage so invalidated contexts never throw
   * synchronously (Chrome may throw before returning a Promise).
   */
  function safeRuntimeSendMessage(message, chromeApi = globalThis.chrome) {
    if (!isExtensionContextValid(chromeApi)) {
      return Promise.reject(invalidatedError());
    }
    try {
      const result = chromeApi.runtime.sendMessage(message);
      return Promise.resolve(result).catch((error) => {
        if (isExtensionContextInvalidatedError(error)) throw markInvalidated(error);
        throw error;
      });
    } catch (error) {
      if (isExtensionContextInvalidatedError(error)) {
        return Promise.reject(markInvalidated(error));
      }
      return Promise.reject(error);
    }
  }

  /**
   * Fire-and-forget messaging: swallows invalidated / transient errors.
   * Returns true when a message was dispatched, false when skipped or failed.
   */
  function softRuntimeSendMessage(message, chromeApi = globalThis.chrome) {
    return safeRuntimeSendMessage(message, chromeApi).then(
      () => true,
      (error) => {
        if (isExtensionContextInvalidatedError(error) || error?.invalidated) return false;
        return false;
      },
    );
  }

  function safeStorageLocalGet(defaults, chromeApi = globalThis.chrome) {
    if (!isExtensionContextValid(chromeApi)) {
      return Promise.reject(invalidatedError());
    }
    try {
      return Promise.resolve(chromeApi.storage.local.get(defaults)).catch((error) => {
        if (isExtensionContextInvalidatedError(error)) throw markInvalidated(error);
        throw error;
      });
    } catch (error) {
      if (isExtensionContextInvalidatedError(error)) {
        return Promise.reject(markInvalidated(error));
      }
      return Promise.reject(error);
    }
  }

  function safeStorageLocalSet(value, chromeApi = globalThis.chrome) {
    if (!isExtensionContextValid(chromeApi)) {
      return Promise.reject(invalidatedError());
    }
    try {
      return Promise.resolve(chromeApi.storage.local.set(value)).catch((error) => {
        if (isExtensionContextInvalidatedError(error)) throw markInvalidated(error);
        throw error;
      });
    } catch (error) {
      if (isExtensionContextInvalidatedError(error)) {
        return Promise.reject(markInvalidated(error));
      }
      return Promise.reject(error);
    }
  }

  globalThis.MeshiLensRuntime = {
    isExtensionContextValid,
    isExtensionContextInvalidatedError,
    safeRuntimeSendMessage,
    softRuntimeSendMessage,
    safeStorageLocalGet,
    safeStorageLocalSet,
  };
})();
