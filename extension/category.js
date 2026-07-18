(() => {
  const FOOD_CATEGORY_PATTERNS = [
    /(?:餐廳|餐厅|餐館|餐馆|食堂|飯館|饭馆|小吃店|美食廣場|美食广场|咖啡店|咖啡廳|咖啡厅|咖啡館|咖啡馆|茶館|茶馆|茶屋|酒吧|居酒屋|啤酒館|啤酒馆|麵包店|面包店|烘焙坊|甜品店|甜點店|甜点店|冰品店|冰淇淋店|蛋糕店|糕餅店|糕饼店|餅店|饼店|拉麵店|拉面店|三明治店|便當店|便当店|熟食店|外賣店|外卖店|飲料店|饮料店|果汁店|餐飲服務|餐饮服务)/i,
    /(?:\b(?:restaurant|cafe|coffee shop|tea house|tea room|bar|pub|izakaya|diner|eatery|food court|bakery|dessert shop|ice cream shop|donut shop|takeout|meal delivery|caterer|bistro|brasserie|pizzeria|steakhouse|grill|ramen|sushi)\b|café)/i,
    /(?:レストラン|食堂|料理店|飲食店|居酒屋|カフェ|喫茶店|茶屋|バー|パブ|パン屋|ベーカリー|菓子店|ケーキ屋|弁当屋|惣菜店|ラーメン店|寿司店|蕎麦店|うどん店|焼肉店|カレー店)/,
    /(?:음식점|식당|카페|커피숍|술집|바|펍|베이커리|제과점|아이스크림 가게)/,
  ];

  function isFoodCategory(value) {
    const category = String(value || "").normalize("NFKC").trim();
    return Boolean(category && FOOD_CATEGORY_PATTERNS.some((pattern) => pattern.test(category)));
  }

  function foodSignalsFromLabels(values = []) {
    const labels = values
      .filter(Boolean)
      .map((value) => String(value).normalize("NFKC").replace(/\s+/g, " ").trim());
    return {
      hasMenu: labels.some((label) => /^(?:菜單|菜单|メニュー|menu|메뉴)(?:$|[·・:：])/i.test(label)),
      hasPerPersonPrice: labels.some((label) => (
        /(?:每人|1\s*人(?:あたり|当たり)|per\s+person|1인당).*(?:¥|￥|\$|€|£|₩)/i.test(label)
      )),
      offersDineIn: labels.some((label) => (
        /(?:提供內用|提供堂食|可內用|可堂食|店内飲食可|イートイン可|offers?\s+dine-in|dine-in\s+available|매장\s*내\s*식사\s*가능)/i.test(label)
      )),
    };
  }

  function isFoodPlace({ category, hasMenu, hasPerPersonPrice, offersDineIn } = {}) {
    return Boolean(
      isFoodCategory(category)
      || hasMenu
      || hasPerPersonPrice
      || offersDineIn,
    );
  }

  globalThis.MeshiLensCategory = { foodSignalsFromLabels, isFoodCategory, isFoodPlace };
})();
