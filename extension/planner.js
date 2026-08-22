(() => {
  const PLANNER_VERSION = 1;
  const MAX_GROUP_RESTAURANTS = 5;
  const MAX_INBOX_RESTAURANTS = 20;
  const MAX_TRIPS = 10;
  const MAX_GROUPS_PER_TRIP = 12;

  function boundedText(value, limit = 300) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
  }

  function safeWebUrl(value) {
    try {
      const url = new URL(String(value || ""));
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch {
      return "";
    }
  }

  function normalizedMapsUrl(value) {
    try {
      const url = new URL(String(value || ""));
      const match = url.pathname.match(/^(\/maps\/place\/[^/]+)/);
      if (!match) return safeWebUrl(value);
      return `${url.origin}${match[1]}`;
    } catch {
      return "";
    }
  }

  function finiteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function sanitizedAnchor(value) {
    if (!value || typeof value !== "object") return null;
    const name = boundedText(value.name, 160);
    const latitude = finiteNumber(value.latitude);
    const longitude = finiteNumber(value.longitude);
    if (!name && (latitude === null || longitude === null)) return null;
    return { name, latitude, longitude };
  }

  function restaurantFromMatch({ place = {}, candidate = {}, michelin = null } = {}) {
    const mapsUrl = normalizedMapsUrl(place.maps_url || place.mapsUrl || "");
    const tabelogUrl = safeWebUrl(candidate.url || candidate.tabelog_url || "");
    const name = boundedText(candidate.name || place.name, 160);
    const identity = mapsUrl || tabelogUrl || [name, finiteNumber(place.latitude), finiteNumber(place.longitude)].join("|");
    return {
      id: identity,
      name,
      mapsName: boundedText(place.name || name, 160),
      mapsUrl,
      address: boundedText(candidate.address || place.address, 300),
      latitude: finiteNumber(candidate.latitude ?? place.latitude),
      longitude: finiteNumber(candidate.longitude ?? place.longitude),
      tabelogUrl,
      rating: finiteNumber(candidate.rating),
      reviewCount: finiteNumber(candidate.review_count),
      genres: (Array.isArray(candidate.genres) ? candidate.genres : [])
        .map((item) => boundedText(item, 60))
        .filter(Boolean)
        .slice(0, 4),
      station: boundedText(candidate.station, 100),
      lunchPrice: boundedText(candidate.lunch_price, 100),
      dinnerPrice: boundedText(candidate.dinner_price, 100),
      closedDays: boundedText(candidate.closed_days, 200),
      businessHours: boundedText(candidate.business_hours, 500),
      reservationStatus: candidate.reservation_url
        ? "online"
        : boundedText(candidate.reservation_status, 30) || "unknown",
      reservationUrl: safeWebUrl(candidate.reservation_url),
      confidence: boundedText(candidate.confidence, 20),
      hyakumeitenYears: (Array.isArray(candidate.hyakumeiten) ? candidate.hyakumeiten : [])
        .map((item) => Number(item?.year))
        .filter(Number.isFinite)
        .slice(0, 20),
      michelinLabel: boundedText(michelin?.distinction_label || michelin?.label, 80),
      greenStar: michelin?.green_star === true,
      matchStatus: candidate.name ? "ready" : "pending",
    };
  }

  function sanitizeRestaurant(value) {
    if (!value || typeof value !== "object") return null;
    const id = boundedText(value.id, 500);
    const name = boundedText(value.name, 160);
    if (!id || !name) return null;
    return {
      id,
      name,
      mapsName: boundedText(value.mapsName || name, 160),
      mapsUrl: normalizedMapsUrl(value.mapsUrl),
      address: boundedText(value.address, 300),
      latitude: finiteNumber(value.latitude),
      longitude: finiteNumber(value.longitude),
      tabelogUrl: safeWebUrl(value.tabelogUrl),
      rating: finiteNumber(value.rating),
      reviewCount: finiteNumber(value.reviewCount),
      genres: (Array.isArray(value.genres) ? value.genres : [])
        .map((item) => boundedText(item, 60))
        .filter(Boolean)
        .slice(0, 4),
      station: boundedText(value.station, 100),
      lunchPrice: boundedText(value.lunchPrice, 100),
      dinnerPrice: boundedText(value.dinnerPrice, 100),
      closedDays: boundedText(value.closedDays, 200),
      businessHours: boundedText(value.businessHours, 500),
      reservationStatus: ["online", "available", "unavailable", "unknown"].includes(value.reservationStatus)
        ? value.reservationStatus
        : "unknown",
      reservationUrl: safeWebUrl(value.reservationUrl),
      confidence: boundedText(value.confidence, 20),
      hyakumeitenYears: (Array.isArray(value.hyakumeitenYears) ? value.hyakumeitenYears : [])
        .map(Number)
        .filter(Number.isFinite)
        .slice(0, 20),
      michelinLabel: boundedText(value.michelinLabel, 80),
      greenStar: value.greenStar === true,
      matchStatus: ["pending", "ready", "error"].includes(value.matchStatus)
        ? value.matchStatus
        : "ready",
    };
  }

  function uniqueRestaurants(value, limit) {
    const result = [];
    const seen = new Set();
    for (const item of Array.isArray(value) ? value : []) {
      const restaurant = sanitizeRestaurant(item);
      if (!restaurant || seen.has(restaurant.id)) continue;
      seen.add(restaurant.id);
      result.push(restaurant);
      if (result.length === limit) break;
    }
    return result;
  }

  function sanitizePlannerState(value) {
    const empty = createPlannerState();
    if (!value || typeof value !== "object" || value.version !== PLANNER_VERSION) return empty;
    const trips = [];
    const tripIds = new Set();
    for (const rawTrip of Array.isArray(value.trips) ? value.trips : []) {
      const id = boundedText(rawTrip?.id, 120);
      const name = boundedText(rawTrip?.name, 120);
      if (!id || !name || tripIds.has(id) || !Array.isArray(rawTrip.inbox) || !Array.isArray(rawTrip.groups)) {
        continue;
      }
      tripIds.add(id);
      const groups = [];
      const groupIds = new Set();
      for (const rawGroup of rawTrip.groups) {
        const groupId = boundedText(rawGroup?.id, 120);
        const groupName = boundedText(rawGroup?.name, 120);
        if (!groupId || !groupName || groupIds.has(groupId) || !Array.isArray(rawGroup.restaurants)) continue;
        groupIds.add(groupId);
        const restaurants = uniqueRestaurants(rawGroup.restaurants, MAX_GROUP_RESTAURANTS);
        const restaurantIds = new Set(restaurants.map((item) => item.id));
        groups.push({
          id: groupId,
          name: groupName,
          anchor: sanitizedAnchor(rawGroup.anchor),
          date: /^\d{4}-\d{2}-\d{2}$/.test(String(rawGroup.date || "")) ? String(rawGroup.date) : "",
          meal: ["lunch", "dinner"].includes(rawGroup.meal) ? rawGroup.meal : "",
          intent: ["destination", "nearby", "budget"].includes(rawGroup.intent)
            ? rawGroup.intent
            : "destination",
          budgetMax: finiteNumber(rawGroup.budgetMax),
          restaurants,
          primaryId: restaurantIds.has(rawGroup.primaryId) ? rawGroup.primaryId : null,
          backupId: restaurantIds.has(rawGroup.backupId) && rawGroup.backupId !== rawGroup.primaryId
            ? rawGroup.backupId
            : null,
          createdAt: finiteNumber(rawGroup.createdAt) ?? Date.now(),
          updatedAt: finiteNumber(rawGroup.updatedAt) ?? Date.now(),
        });
        if (groups.length === MAX_GROUPS_PER_TRIP) break;
      }
      trips.push({
        id,
        name,
        createdAt: finiteNumber(rawTrip.createdAt) ?? Date.now(),
        updatedAt: finiteNumber(rawTrip.updatedAt) ?? Date.now(),
        inbox: uniqueRestaurants(rawTrip.inbox, MAX_INBOX_RESTAURANTS),
        groups,
      });
      if (trips.length === MAX_TRIPS) break;
    }
    const activeTrip = trips.find((trip) => trip.id === value.activeTripId) || trips[0] || null;
    const activeGroup = activeTrip?.groups.find((group) => group.id === value.activeGroupId) || null;
    return {
      version: PLANNER_VERSION,
      activeTripId: activeTrip?.id || null,
      activeGroupId: activeGroup?.id || null,
      trips,
    };
  }

  function createPlannerState() {
    return {
      version: PLANNER_VERSION,
      activeTripId: null,
      activeGroupId: null,
      trips: [],
    };
  }

  function createTrip(state, input = {}) {
    const now = Number.isFinite(input.now) ? input.now : Date.now();
    const trip = {
      id: String(input.id || "").trim(),
      name: String(input.name || "").trim(),
      createdAt: now,
      updatedAt: now,
      inbox: [],
      groups: [],
    };
    if (
      !trip.id
      || !trip.name
      || state.trips.length >= MAX_TRIPS
      || state.trips.some((item) => item.id === trip.id)
    ) return state;
    return {
      ...state,
      activeTripId: trip.id,
      activeGroupId: null,
      trips: [...state.trips, trip],
    };
  }

  function createGroup(state, tripId, input = {}) {
    const id = String(input.id || "").trim();
    const name = String(input.name || "").trim();
    if (!id || !name) return state;
    const now = Number.isFinite(input.now) ? input.now : Date.now();
    const group = {
      id,
      name,
      anchor: sanitizedAnchor(input.anchor),
      date: String(input.date || ""),
      meal: String(input.meal || ""),
      intent: String(input.intent || "destination"),
      budgetMax: Number.isFinite(input.budgetMax) ? input.budgetMax : null,
      restaurants: [],
      primaryId: null,
      backupId: null,
      createdAt: now,
      updatedAt: now,
    };
    let created = false;
    const trips = state.trips.map((trip) => {
      if (
        trip.id !== tripId
        || trip.groups.length >= MAX_GROUPS_PER_TRIP
        || trip.groups.some((item) => item.id === id)
      ) return trip;
      created = true;
      return { ...trip, groups: [...trip.groups, group], updatedAt: now };
    });
    return created
      ? { ...state, trips, activeTripId: tripId, activeGroupId: id }
      : state;
  }

  function ensureActiveMeal(state, tripId, input = {}) {
    const trip = state.trips.find((item) => item.id === tripId);
    if (!trip) return state;
    if (
      state.activeTripId === tripId
      && state.activeGroupId
      && trip.groups.some((group) => group.id === state.activeGroupId)
    ) return state;
    if (trip.groups.length) return state;
    const id = String(input.id || "").trim();
    if (!id) return state;
    return createGroup(state, tripId, {
      id,
      name: boundedText(input.name || "第一餐", 120) || "第一餐",
      now: input.now,
    });
  }

  function updateGroup(state, tripId, groupId, input = {}, options = {}) {
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId) return trip;
      const groups = trip.groups.map((group) => {
        if (group.id !== groupId) return group;
        const intent = input.intent !== undefined
          ? (["destination", "nearby", "budget"].includes(input.intent) ? input.intent : group.intent)
          : group.intent;
        const meal = input.meal !== undefined
          ? (["lunch", "dinner"].includes(input.meal) ? input.meal : "")
          : group.meal;
        const budgetMax = input.budgetMax !== undefined
          ? (input.budgetMax === "" || input.budgetMax == null ? null : finiteNumber(input.budgetMax))
          : group.budgetMax;
        const name = input.name !== undefined
          ? (boundedText(input.name, 120) || group.name)
          : group.name;
        const date = input.date !== undefined
          ? (/^\d{4}-\d{2}-\d{2}$/.test(String(input.date || "")) ? String(input.date) : "")
          : group.date;
        const anchor = input.anchor !== undefined ? sanitizedAnchor(input.anchor) : group.anchor;
        if (
          name === group.name
          && date === group.date
          && meal === group.meal
          && intent === group.intent
          && budgetMax === group.budgetMax
          && JSON.stringify(anchor) === JSON.stringify(group.anchor)
        ) return group;
        changed = true;
        return {
          ...group,
          name,
          anchor,
          date,
          meal,
          intent,
          budgetMax,
          updatedAt: now,
        };
      });
      return changed ? { ...trip, groups, updatedAt: now } : trip;
    });
    return changed ? { ...state, trips, activeTripId: tripId, activeGroupId: groupId } : state;
  }

  function upsertRestaurant(items, restaurant, limit) {
    if (!restaurant?.id || !restaurant?.name) return items;
    const index = items.findIndex((item) => item.id === restaurant.id);
    if (index >= 0) {
      return items.map((item, itemIndex) => itemIndex === index ? restaurant : item);
    }
    return items.length < limit ? [...items, restaurant] : items;
  }

  function addRestaurant(state, tripId, groupId, restaurant, options = {}) {
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId) return trip;
      if (!groupId) {
        const inbox = upsertRestaurant(trip.inbox, restaurant, MAX_INBOX_RESTAURANTS);
        if (inbox === trip.inbox) return trip;
        changed = true;
        return { ...trip, inbox, updatedAt: now };
      }
      const groups = trip.groups.map((group) => {
        if (group.id !== groupId) return group;
        const restaurants = upsertRestaurant(group.restaurants, restaurant, MAX_GROUP_RESTAURANTS);
        if (restaurants === group.restaurants) return group;
        changed = true;
        return { ...group, restaurants, updatedAt: now };
      });
      return changed ? { ...trip, groups, updatedAt: now } : trip;
    });
    return changed
      ? { ...state, trips, activeTripId: tripId, activeGroupId: groupId || null }
      : state;
  }

  function moveRestaurant(state, tripId, restaurantId, fromGroupId, toGroupId, options = {}) {
    if (fromGroupId === toGroupId) return state;
    const trip = state.trips.find((item) => item.id === tripId);
    if (!trip) return state;
    const source = fromGroupId
      ? trip.groups.find((group) => group.id === fromGroupId)?.restaurants
      : trip.inbox;
    const restaurant = source?.find((item) => item.id === restaurantId);
    if (!restaurant) return state;
    const destination = toGroupId
      ? trip.groups.find((group) => group.id === toGroupId)?.restaurants
      : trip.inbox;
    const limit = toGroupId ? MAX_GROUP_RESTAURANTS : MAX_INBOX_RESTAURANTS;
    if (!destination || (destination.length >= limit && !destination.some((item) => item.id === restaurantId))) {
      return state;
    }
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    const trips = state.trips.map((item) => {
      if (item.id !== tripId) return item;
      let inbox = item.inbox;
      let groups = item.groups.map((group) => ({ ...group }));
      if (!fromGroupId) {
        inbox = inbox.filter((entry) => entry.id !== restaurantId);
      } else {
        groups = groups.map((group) => group.id === fromGroupId
          ? {
              ...group,
              restaurants: group.restaurants.filter((entry) => entry.id !== restaurantId),
              primaryId: group.primaryId === restaurantId ? null : group.primaryId,
              backupId: group.backupId === restaurantId ? null : group.backupId,
              updatedAt: now,
            }
          : group);
      }
      if (!toGroupId) {
        inbox = upsertRestaurant(inbox, restaurant, MAX_INBOX_RESTAURANTS);
      } else {
        groups = groups.map((group) => group.id === toGroupId
          ? {
              ...group,
              restaurants: upsertRestaurant(group.restaurants, restaurant, MAX_GROUP_RESTAURANTS),
              updatedAt: now,
            }
          : group);
      }
      return { ...item, inbox, groups, updatedAt: now };
    });
    return {
      ...state,
      trips,
      activeTripId: tripId,
      activeGroupId: toGroupId || null,
    };
  }

  function clamp(value, minimum = 0, maximum = 1) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function destinationScore(restaurant) {
    const rating = Number.isFinite(restaurant.rating)
      ? clamp((restaurant.rating - 3) / 1.2)
      : null;
    const reviews = Number.isFinite(restaurant.reviewCount)
      ? clamp(Math.log10(restaurant.reviewCount + 1) / 4)
      : null;
    const years = Array.isArray(restaurant.hyakumeitenYears)
      ? restaurant.hyakumeitenYears.length
      : 0;
    const award = restaurant.michelinLabel
      ? 1
      : years
        ? clamp(years / 3)
        : null;
    const confidence = restaurant.confidence ? (restaurant.confidence === "high" ? 1 : 0.35) : null;
    const metrics = [
      [rating, 0.35],
      [reviews, 0.2],
      [award, 0.3],
      [confidence, 0.15],
    ].filter(([value]) => value !== null);
    const weight = metrics.reduce((total, [, itemWeight]) => total + itemWeight, 0);
    return weight
      ? metrics.reduce((total, [value, itemWeight]) => total + value * itemWeight, 0) / weight
      : 0;
  }

  function radians(value) {
    return value * Math.PI / 180;
  }

  function distanceKmBetween(left, right) {
    if (
      !Number.isFinite(left?.latitude)
      || !Number.isFinite(left?.longitude)
      || !Number.isFinite(right?.latitude)
      || !Number.isFinite(right?.longitude)
    ) return null;
    const latitudeDistance = radians(right.latitude - left.latitude);
    const longitudeDistance = radians(right.longitude - left.longitude);
    const startLatitude = radians(left.latitude);
    const endLatitude = radians(right.latitude);
    const value = Math.sin(latitudeDistance / 2) ** 2
      + Math.cos(startLatitude) * Math.cos(endLatitude) * Math.sin(longitudeDistance / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function lowerPrice(value) {
    const match = String(value || "").match(/([\d,]+)/);
    if (!match) return null;
    const price = Number(match[1].replace(/,/g, ""));
    return Number.isFinite(price) ? price : null;
  }

  function nearbyScore(restaurant, distanceKm, meal) {
    const rating = Number.isFinite(restaurant.rating)
      ? clamp((restaurant.rating - 3) / 1.2)
      : null;
    const reviews = Number.isFinite(restaurant.reviewCount)
      ? clamp(Math.log10(restaurant.reviewCount + 1) / 4)
      : null;
    const distance = Number.isFinite(distanceKm) ? clamp(1 - distanceKm / 5) : null;
    const priceYen = lowerPrice(meal === "dinner" ? restaurant.dinnerPrice : restaurant.lunchPrice);
    const price = Number.isFinite(priceYen) ? clamp(1 - priceYen / 30_000) : null;
    const confidence = restaurant.confidence ? (restaurant.confidence === "high" ? 1 : 0.35) : null;
    const metrics = [
      [distance, 0.45],
      [rating, 0.25],
      [reviews, 0.1],
      [price, 0.1],
      [confidence, 0.1],
    ].filter(([value]) => value !== null);
    const weight = metrics.reduce((total, [, itemWeight]) => total + itemWeight, 0);
    return weight
      ? metrics.reduce((total, [value, itemWeight]) => total + value * itemWeight, 0) / weight
      : 0;
  }

  function budgetScore(restaurant, distanceKm, meal) {
    const rating = Number.isFinite(restaurant.rating)
      ? clamp((restaurant.rating - 3) / 1.2)
      : null;
    const reviews = Number.isFinite(restaurant.reviewCount)
      ? clamp(Math.log10(restaurant.reviewCount + 1) / 4)
      : null;
    const distance = Number.isFinite(distanceKm) ? clamp(1 - distanceKm / 10) : null;
    const priceYen = lowerPrice(meal === "dinner" ? restaurant.dinnerPrice : restaurant.lunchPrice);
    const price = Number.isFinite(priceYen) ? clamp(1 - priceYen / 30_000) : null;
    const confidence = restaurant.confidence ? (restaurant.confidence === "high" ? 1 : 0.35) : null;
    const metrics = [
      [price, 0.5],
      [rating, 0.25],
      [reviews, 0.1],
      [distance, 0.05],
      [confidence, 0.1],
    ].filter(([value]) => value !== null);
    const weight = metrics.reduce((total, [, itemWeight]) => total + itemWeight, 0);
    return weight
      ? metrics.reduce((total, [value, itemWeight]) => total + value * itemWeight, 0) / weight
      : 0;
  }

  function yen(value) {
    return `¥${Number(value).toLocaleString("en-US")}`;
  }

  function rankGroup(group = {}) {
    const restaurants = Array.isArray(group.restaurants) ? group.restaurants : [];
    const ratings = restaurants.map((item) => item.rating).filter(Number.isFinite);
    const maxRating = ratings.length ? Math.max(...ratings) : null;
    const distances = restaurants.map((restaurant) => distanceKmBetween(group.anchor, restaurant));
    const knownDistances = distances.filter(Number.isFinite);
    const minDistance = knownDistances.length ? Math.min(...knownDistances) : null;
    const prices = restaurants.map((restaurant) => lowerPrice(
      group.meal === "dinner" ? restaurant.dinnerPrice : restaurant.lunchPrice,
    ));
    const knownPrices = prices.filter(Number.isFinite);
    const minPrice = knownPrices.length ? Math.min(...knownPrices) : null;
    return restaurants
      .map((restaurant, index) => {
        const advantages = [];
        const distanceKm = distances[index];
        const priceYen = prices[index];
        if (group.intent === "budget" && minPrice !== null && priceYen === minPrice) {
          advantages.push(`${group.meal === "dinner" ? "晚餐" : "午餐"}預算較輕（${yen(priceYen)} 起）`);
        }
        if (group.intent === "nearby" && minDistance !== null && distanceKm === minDistance) {
          advantages.push(distanceKm < 0.05
            ? "就在集合點附近"
            : `距離集合點最近（約 ${Math.round(distanceKm * 10) / 10} 公里）`);
        }
        if (maxRating !== null && restaurant.rating === maxRating) {
          advantages.push(`Tabelog 評分最高（${restaurant.rating.toFixed(2)}）`);
        }
        if (restaurant.michelinLabel) advantages.push(`Michelin ${restaurant.michelinLabel}`);
        const years = Array.isArray(restaurant.hyakumeitenYears)
          ? restaurant.hyakumeitenYears.length
          : 0;
        if (years) advantages.push(`百名店入選 ${years} 年`);
        const cautions = [];
        if (!Number.isFinite(restaurant.rating)) cautions.push("Tabelog 評分未知");
        if (restaurant.confidence && restaurant.confidence !== "high") cautions.push("請再次確認店家配對");
        if (group.intent === "nearby" && !Number.isFinite(distanceKm)) cautions.push("缺少與集合點的距離");
        if (group.intent === "budget" && !Number.isFinite(priceYen)) cautions.push("缺少所選餐期價位");
        if (
          group.intent === "budget"
          && Number.isFinite(group.budgetMax)
          && Number.isFinite(priceYen)
          && priceYen > group.budgetMax
        ) cautions.push(`超過設定預算 ${yen(group.budgetMax)}`);
        return {
          restaurant,
          advantages,
          cautions,
          distanceKm,
          priceYen,
          score: group.intent === "nearby"
            ? nearbyScore(restaurant, distanceKm, group.meal)
            : group.intent === "budget"
              ? budgetScore(restaurant, distanceKm, group.meal)
              : destinationScore(restaurant),
          originalIndex: index,
        };
      })
      .sort((left, right) => right.score - left.score || left.originalIndex - right.originalIndex)
      .map(({ originalIndex: _originalIndex, ...item }) => item);
  }

  function chooseRestaurant(state, tripId, groupId, restaurantId, role, options = {}) {
    if (role !== "primary" && role !== "backup") return state;
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId) return trip;
      const groups = trip.groups.map((group) => {
        if (group.id !== groupId || !group.restaurants.some((item) => item.id === restaurantId)) {
          return group;
        }
        changed = true;
        return {
          ...group,
          primaryId: role === "primary"
            ? restaurantId
            : group.primaryId === restaurantId ? null : group.primaryId,
          backupId: role === "backup"
            ? restaurantId
            : group.backupId === restaurantId ? null : group.backupId,
          updatedAt: now,
        };
      });
      return changed ? { ...trip, groups, updatedAt: now } : trip;
    });
    return changed ? { ...state, trips, activeTripId: tripId, activeGroupId: groupId } : state;
  }

  function removeRestaurant(state, tripId, groupId, restaurantId, options = {}) {
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId) return trip;
      if (!groupId) {
        const inbox = trip.inbox.filter((item) => item.id !== restaurantId);
        if (inbox.length === trip.inbox.length) return trip;
        changed = true;
        return { ...trip, inbox, updatedAt: now };
      }
      const groups = trip.groups.map((group) => {
        if (group.id !== groupId) return group;
        const restaurants = group.restaurants.filter((item) => item.id !== restaurantId);
        if (restaurants.length === group.restaurants.length) return group;
        changed = true;
        return {
          ...group,
          restaurants,
          primaryId: group.primaryId === restaurantId ? null : group.primaryId,
          backupId: group.backupId === restaurantId ? null : group.backupId,
          updatedAt: now,
        };
      });
      return changed ? { ...trip, groups, updatedAt: now } : trip;
    });
    return changed ? { ...state, trips } : state;
  }

  function deleteGroup(state, tripId, groupId, options = {}) {
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId) return trip;
      const removed = trip.groups.find((group) => group.id === groupId);
      if (!removed) return trip;
      changed = true;
      let inbox = trip.inbox;
      for (const restaurant of removed.restaurants) {
        inbox = upsertRestaurant(inbox, restaurant, MAX_INBOX_RESTAURANTS);
      }
      return {
        ...trip,
        inbox,
        groups: trip.groups.filter((group) => group.id !== groupId),
        updatedAt: now,
      };
    });
    if (!changed) return state;
    return {
      ...state,
      trips,
      activeTripId: tripId,
      activeGroupId: state.activeTripId === tripId && state.activeGroupId === groupId
        ? null
        : state.activeGroupId,
    };
  }

  function setActiveTarget(state, tripId, groupId = null) {
    const trip = state.trips.find((item) => item.id === tripId);
    if (!trip) return state;
    if (groupId && !trip.groups.some((group) => group.id === groupId)) return state;
    return { ...state, activeTripId: tripId, activeGroupId: groupId || null };
  }

  function renameTrip(state, tripId, name, options = {}) {
    const nextName = boundedText(name, 120);
    if (!nextName) return state;
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    let changed = false;
    const trips = state.trips.map((trip) => {
      if (trip.id !== tripId || trip.name === nextName) return trip;
      changed = true;
      return { ...trip, name: nextName, updatedAt: now };
    });
    return changed ? { ...state, trips } : state;
  }

  function deleteTrip(state, tripId) {
    if (!state.trips.some((trip) => trip.id === tripId)) return state;
    const trips = state.trips.filter((trip) => trip.id !== tripId);
    if (state.activeTripId !== tripId) return { ...state, trips };
    const nextTrip = trips[0] || null;
    return {
      ...state,
      trips,
      activeTripId: nextTrip?.id || null,
      activeGroupId: nextTrip?.groups[0]?.id || null,
    };
  }

  globalThis.MeshiLensPlanner = {
    PLANNER_VERSION,
    MAX_GROUP_RESTAURANTS,
    MAX_INBOX_RESTAURANTS,
    MAX_TRIPS,
    MAX_GROUPS_PER_TRIP,
    createPlannerState,
    sanitizePlannerState,
    createTrip,
    createGroup,
    ensureActiveMeal,
    updateGroup,
    restaurantFromMatch,
    addRestaurant,
    moveRestaurant,
    rankGroup,
    distanceKmBetween,
    chooseRestaurant,
    removeRestaurant,
    deleteGroup,
    setActiveTarget,
    renameTrip,
    deleteTrip,
  };
})();
