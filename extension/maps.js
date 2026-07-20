(() => {
  const COORDINATE_PATTERN = /!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/g;
  const VIEWPORT_PATTERN = /\/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/;

  function coordinatesFromMapsUrl(value) {
    const url = String(value || "");
    const placeCoordinates = Array.from(url.matchAll(COORDINATE_PATTERN));
    const placeMatch = placeCoordinates[placeCoordinates.length - 1];
    if (placeMatch) {
      return {
        latitude: Number(placeMatch[1]),
        longitude: Number(placeMatch[2]),
        coordinates_source: "place",
      };
    }
    const viewportMatch = url.match(VIEWPORT_PATTERN);
    return viewportMatch
      ? {
        latitude: Number(viewportMatch[1]),
        longitude: Number(viewportMatch[2]),
        coordinates_source: "viewport",
      }
      : { latitude: null, longitude: null, coordinates_source: "" };
  }

  globalThis.MeshiLensMaps = { coordinatesFromMapsUrl };
})();
