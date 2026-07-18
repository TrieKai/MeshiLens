(() => {
  const COORDINATE_PATTERN = /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/g;
  const VIEWPORT_PATTERN = /\/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/;

  function coordinatesFromMapsUrl(value) {
    const url = String(value || "");
    const placeCoordinates = Array.from(url.matchAll(COORDINATE_PATTERN));
    const match = placeCoordinates[placeCoordinates.length - 1] || url.match(VIEWPORT_PATTERN);
    return match
      ? { latitude: Number(match[1]), longitude: Number(match[2]) }
      : { latitude: null, longitude: null };
  }

  globalThis.MeshiLensMaps = { coordinatesFromMapsUrl };
})();
