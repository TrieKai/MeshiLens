(() => {
  const FOOD_CATEGORY_PATTERNS = [
    /(?:餐廳|餐厅|餐館|餐馆|食堂|飯館|饭馆|小吃店|美食廣場|美食广场|咖啡店|咖啡廳|咖啡厅|咖啡館|咖啡馆|茶館|茶馆|茶屋|酒吧|居酒屋|啤酒館|啤酒馆|麵包店|面包店|烘焙坊|甜品店|甜點店|甜点店|冰品店|冰淇淋店|蛋糕店|糕餅店|糕饼店|便當店|便当店|熟食店|外賣店|外卖店|飲料店|饮料店|果汁店|餐飲服務|餐饮服务)/i,
    /(?:\b(?:restaurant|cafe|coffee shop|tea house|tea room|bar|pub|izakaya|diner|eatery|food court|bakery|dessert shop|ice cream shop|donut shop|takeout|meal delivery|caterer|bistro|brasserie|pizzeria|steakhouse|grill|ramen|sushi)\b|café)/i,
    /(?:レストラン|食堂|料理店|飲食店|居酒屋|カフェ|喫茶店|茶屋|バー|パブ|パン屋|ベーカリー|菓子店|ケーキ屋|弁当屋|惣菜店|ラーメン店|寿司店|蕎麦店|うどん店|焼肉店|カレー店)/,
    /(?:음식점|식당|카페|커피숍|술집|바|펍|베이커리|제과점|아이스크림 가게)/,
  ];

  function isFoodCategory(value) {
    const category = String(value || "").normalize("NFKC").trim();
    return Boolean(category && FOOD_CATEGORY_PATTERNS.some((pattern) => pattern.test(category)));
  }

  globalThis.MeshiLensCategory = { isFoodCategory };
})();
