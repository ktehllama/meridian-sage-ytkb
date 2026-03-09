/**
 * Channel category mapping.
 * Keys: display category names.
 * Values: comma-separated YouTube handles (no @, lowercase).
 *
 * Matching is fuzzy — getCategoryForChannel does partial matching so
 * slight handle variations in the DB (e.g. with/without @) still resolve.
 */
export const CHANNEL_CATEGORIES: Record<string, string[]> = {
  'AI / Tech': [
    'ycombinator', 'andrejkarpathy', 'yannickilcher', 'computerphile',
    'twominutepapers', 'lexfridman', 'geohotarchive', 'aiexplained-official',
    'aiexplained', 'sabinehossenfelder', '3blue1brown', 'sebastianlague',
  ],
  'Business': [
    'acquiredfm', 'davidsenra', 'coldfusion', 'a16z', 'valuetainment',
    'harvardbusinessreview', 'garrytan', 'myfirstmillionpod',
  ],
  'Investing / Finance': [
    'pboyle', 'theplainbagel', 'aswathdamodaranonvaluation', 'theinvestorspodcast',
    'westudybillionaires', 'oddlots', 'economicsexplained',
  ],
  'Science': [
    'veritasium', 'kurzgesagt', 'pbsspacetime', 'realengineering',
    'practicalengineeringchannel', 'scishow', 'fermilab',
  ],
  'Psychology': [
    'robertsapolskypodcast', 'jordanbpeterson', 'sprouts', 'modernwisdompodcast',
    'talksatgoogle', 'bigthink', 'danielkahneman',
  ],
  'Health': [
    'hubermanlab', 'peterattiamd', 'jeffnippard', 'thomasdelauerofficial',
    'thomasdelauer', 'foundmyfitness', 'bryanjohnson',
  ],
  'History': [
    'wendoverproductions', 'reallifelore', 'caspianreport', 'kingsandgenerals',
    'fallofcivilizations', 'oversimplified', 'asianometry', 'historyoftheearth',
  ],
  'Marketing': [
    'marketingagainstthegrain', 'garyvee', 'alexhormozi', 'saastr',
    'microconf', 'cxlinstitute', 'davidperell',
  ],
  'Product / Design': [
    'figma', 'uxmastery', 'nerdwriter1', 'thomasflight', 'mizko',
    'googledesign', 'stripepress',
  ],
  'Leadership': [
    'simonsinek', 'jockowillink', 'stanfordgsb', 'mitocw', 'firstround',
  ],
  'Philosophy': [
    'einzelganger', 'academyofideas', 'likestoriesofold', 'sisyphus55',
    'thenandnow', 'philosophizethis', 'theschooloflife',
  ],
  'Law': [
    'legaleagle', 'coinbureau', 'stanfordlaw', 'lawfare', 'jakechervinsk',
  ],
  'Real Estate': [
    'biggerpockets', 'grahamstephan', 'meetkevin', 'kenmcelroyre', 'realvision',
  ],
  'Communication': [
    'charismaoncommand', 'jeffersonfisher', 'ted', 'tedx', 'chrisvoss', 'vanur',
  ],
  'Productivity': [
    'aliabdaal', 'thomasfrankexplains', 'justinsung', 'mattdavella',
    'mikeandmatty', 'cgpgrey',
  ],
};

/** All category names in display order. */
export const ALL_CATEGORIES = Object.keys(CHANNEL_CATEGORIES);

/**
 * Returns the category name for a given channel handle, or null if unknown.
 * Matching is fuzzy: strips @, lowercases, checks if either string contains the other.
 */
export function getCategoryForChannel(handle: string): string | null {
  const normalized = handle.replace(/^@/, '').toLowerCase();
  for (const [cat, handles] of Object.entries(CHANNEL_CATEGORIES)) {
    if (handles.some((h) => normalized.includes(h) || h.includes(normalized))) {
      return cat;
    }
  }
  return null;
}
