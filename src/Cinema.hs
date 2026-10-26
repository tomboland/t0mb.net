{-# LANGUAGE OverloadedStrings #-}
-- Cinema records and template contexts. Presentation belongs in templates/.
module Cinema where

import View

import Control.Monad (forM, unless, when)
import Data.Aeson (Value(..), Result(..), fromJSON, eitherDecodeStrict')
import qualified Data.ByteString as BS
import Data.Char (isAscii, isAlphaNum)
import Data.List (sortOn, groupBy, isPrefixOf, intercalate)
import qualified Data.Map.Strict as M
import Data.Maybe (fromMaybe)
import Data.Ord (Down(..))
import qualified Data.Set as S
import qualified Data.Text as T
import Data.Time (Day, defaultTimeLocale, parseTimeM)
import System.Directory (listDirectory, doesFileExist)
import System.FilePath ((</>), takeExtension, splitDirectories)

filmUrl :: Value -> String
filmUrl f = "/films/" ++ str "slug" f ++ "/"
directorUrl :: Value -> String
directorUrl p = "/directors/" ++ slug (str "name" p) ++ "-" ++ str "id" p ++ "/"
tagUrl :: String -> String
tagUrl = tagUrlIn "/films/tags/"

-- Retain every review's path, including drafts, so validation runs before routing.
data Cinema = Cinema { films :: [Value], viewings :: [Value], people :: [Value], reviews :: [Value], artwork :: Value, collection :: Value, diaryNotes :: [Value], ownedReleaseRows :: [Value], legacyWorkLinks :: M.Map String String, releaseLinks :: M.Map String [Value] }

readJson :: FilePath -> IO Value
readJson path = BS.readFile path >>= either (fail . ((path ++ ": ") ++)) pure . eitherDecodeStrict'
loadCinema :: IO Cinema
loadCinema = do
  fs <- arr <$> readJson "cinema/films.json"
  vs <- arr <$> readJson "cinema/viewings.json"
  collectionExists <- doesFileExist "cinema/collection.json"
  cs <- if collectionExists then readJson "cinema/collection.json" else pure Null
  aliasesExist <- doesFileExist "cinema/collection-redirects.json"
  aliases <- if aliasesExist then do
    raw <- readJson "cinema/collection-redirects.json"
    case fromJSON raw of
      Success links -> pure links
      Error err -> fail err
    else pure M.empty
  noteExists <- doesFileExist "cinema/entries.json"
  ns <- if noteExists then arr <$> readJson "cinema/entries.json" else pure []
  ps <- arr <$> readJson "cinema/directors.json"
  names <- sortOn id <$> listDirectory "cinema/reviews"
  rs <- mapM (readDocument . ("cinema/reviews" </>)) $ filter ((==".md") . takeExtension) names
  exists <- doesFileExist "cinema/artwork.json"
  artworkData <- if exists then readJson "cinema/artwork.json" else pure Null
  tagged <- forM fs $ \f -> either fail (\ts -> pure $ set [("tags",values $ map val ts)] f) (normalTags $ get "tags" f)
  let ownedIds=S.fromList [str "edition_id" x|x<-ls "copies" cs,copyIsOwned x]
      releases=[e|e<-ls "editions" cs,S.member (str "id" e) ownedIds]
      links=M.fromListWith (++) [(fid,[e])|e<-releases,fid<-S.toList $ S.fromList [str "film" entry|entry<-ls "contents" e],not $ null fid]
      c = Cinema tagged vs ps rs artworkData cs ns releases aliases links
  validate c
  pure c

validate :: Cinema -> IO ()
validate c = do
  unique "film IDs" (map (str "id") $ films c)
  unique "film slugs" (map (str "slug") $ films c)
  unique "viewing IDs" (map (str "id") $ viewings c)
  unique "diary note IDs" (map (str "id") $ diaryNotes c)
  unique "review IDs" (map (str "id") $ reviews c)
  let ids = S.fromList $ map (str "id") $ films c
      notes = M.fromList [(str "id" v,str "film" v) | v <- diaryNotes c]
      watches = M.fromList [(str "id" v,str "film" v) | v <- viewings c]
  let coll=collection c
      es=ls "editions" coll
      cs=ls "copies" coll
      editionIds=S.fromList $ map (str "id") es
  mapM_ (\(label,rows) -> do
    unique label (map (str "id") rows)
    unless (all (safeSlug . str "id") rows) $ fail ("Unsafe "++label)) [("edition IDs",es),("copy IDs",cs)]
  unless (null $ ls "works" coll) $ fail "Obsolete collection work identities"
  mapM_ (\(old,fid) -> unless (safeSlug old && S.member fid ids) $ fail "Invalid collection URL alias") $ M.toList $ legacyWorkLinks c
  mapM_ (\e -> unless (all ((`S.member` ids).str "film") $ ls "contents" e) $ fail "Edition refers to missing film") es
  mapM_ (\x -> unless (S.member (str "edition_id" x) editionIds) $ fail "Copy refers to missing edition") cs
  mapM_ (\f -> do
    unless (safeSlug $ str "slug" f) $ fail "Invalid film slug"
    unless (get "liked" f `elem` [Null,Bool True,Bool False]) $ fail "liked must be true or false"
    case get "theme" f of
      Null -> pure ()
      String theme | safeSlug (T.unpack theme) -> pure ()
      _ -> fail "Film theme must be a non-empty lowercase name using letters, digits or hyphens"
    validRating f) (films c)
  mapM_ (\v -> do
    unless (S.member (str "film" v) ids) $ fail "Viewing refers to missing film"
    validDate "date" v; validRating v) (viewings c)
  mapM_ (\n -> do
    unless (S.member (str "film" n) ids) $ fail "Diary note refers to missing film"
    validDate "date" n) (diaryNotes c)
  mapM_ (\r -> do
    unless (S.member (str "film" r) ids) $ fail "Review refers to missing film"
    unless (all (\x -> isAscii x && (isAlphaNum x || x=='-')) (str "id" r) && not (null $ str "id" r)) $ fail "Unsafe review ID"
    mapM_ (\key -> unless (get key r `elem` [Null,Bool True,Bool False]) $ fail (key ++ " must be true or false")) ["draft","featured"]
    when (truth $ get "viewing" r) $ unless (M.lookup (str "viewing" r) watches == Just (str "film" r)) $ fail "Review viewing belongs to another film"
    when (truth (get "diary_entry" r) && truth (get "viewing" r)) $ fail "Review cannot link both a viewing and a note"
    when (truth $ get "diary_entry" r) $ unless (M.lookup (str "diary_entry" r) notes == Just (str "film" r)) $ fail "Review diary note belongs to another film"
    validDate "date" r
    when (truth $ get "watched_date" r) $ validDate "watched_date" r
    validRating r
    when (published r && null (words $ stripComments $ str "rawBody" r)) $ fail "Published review has no text") (reviews c)
  mapM_ validateImage $ concatMap (\f -> [hero c f, obj [("path",thumbnail c f),("alt",val "Thumbnail")]]) (films c)
  mapM_ (validateImage . reviewImage) $ filter published $ reviews c
  where
    unique label xs = unless (length xs==S.size (S.fromList xs) && all (not.null) xs) $ fail ("Duplicate/empty "++label)
    safeSlug s = not (null s) && all (\x -> x `elem` ['a'..'z']++['0'..'9']++"-") s
    validDate key v = case (parseTimeM True defaultTimeLocale "%Y-%m-%d" (str key v) :: Maybe Day) of Nothing -> fail ("Invalid date: "++str key v); Just _ -> pure ()
    validRating v = when (truth $ get "rating" v) $ case reads (str "rating" v) :: [(Double,String)] of
      [(n,"")] | n>=0.5 && n<=5 && fromIntegral (round (n*2) :: Int)==n*2 -> pure ()
      _ -> fail "Invalid rating"

stripComments :: String -> String
stripComments [] = []
stripComments s | "<!--" `isPrefixOf` s = skip (drop 4 s)
  where skip [] = []; skip x | "-->" `isPrefixOf` x = stripComments (drop 3 x); skip (_:xs) = skip xs
stripComments (x:xs) = x:stripComments xs
published :: Value -> Bool
published r = get "draft" r /= Bool True
validateImage :: Value -> IO ()
validateImage img = when (truth $ get "path" img) $ do
  let p = str "path" img
  unless ("/images/" `isPrefixOf` p && ".." `notElem` splitDirectories p) $ fail ("Unsafe image path: "++p)
  exists <- doesFileExist (drop 1 p)
  unless (exists && truth (get "alt" img)) $ fail ("Image missing or lacking alt text: "++p)

art :: Cinema -> String -> Value -> Value
art c kind f = case get imageField f of
  Null -> get kind $ get (str "id" f) $ artwork c
  v | not (truth v) -> Null
  v -> obj [("path",v),("thumbnail",if truth (get "thumbnail" f) then get "thumbnail" f else v),
            ("alt",if truth (get (imageField++"_alt") f) then get (imageField++"_alt") f else if kind=="poster" then val ("Poster for "++str "title" f) else Null),
            ("caption",get (imageField++"_caption") f)]
  where imageField = if kind=="poster" then "poster" else "image"
thumbnail :: Cinema -> Value -> Value
thumbnail c f = case get "thumbnail" f of
  Null -> let p = art c "poster" f in if truth (get "thumbnail" p) then get "thumbnail" p else get "path" p
  v -> if truth v then v else Null
hero :: Cinema -> Value -> Value
hero c f = let backdrop=art c "backdrop" f; poster=art c "poster" f
               chosen=if truth backdrop then backdrop else if get "image" f==Null then poster else Null
           in if truth chosen then set [("isPoster",Bool (chosen==poster))] chosen else Null
reviewImage :: Value -> Value
reviewImage r = if truth (get "image" r) then obj [("path",get "image" r),("alt",get "image_alt" r),("caption",get "image_caption" r)] else Null

latestReviews :: Cinema -> [Value]
latestReviews = sortOn (Down . (\r -> (str "date" r,str "id" r))) . filter published . reviews
filmFor :: Cinema -> String -> Value
filmFor c key = fromMaybe (error "Unknown film") $ M.lookup key $ M.fromList [(str "id" f,f) | f <- films c]
reviewUrl :: Cinema -> Value -> String
reviewUrl c r = filmUrl (filmFor c $ str "film" r) ++ "reviews/" ++ str "id" r ++ "/"
reviewSummary :: Cinema -> Value -> Value
reviewSummary c r = set [("liked",get "liked" $ filmFor c $ str "film" r),("url",val $ reviewUrl c r),("thumbnail",thumbnail c $ filmFor c $ str "film" r)] r
ownReviews :: Cinema -> Value -> [Value]
ownReviews c f = filter ((==str "id" f) . str "film") $ latestReviews c
filmSummary :: Cinema -> Value -> Value
filmSummary c f = set [("owned",Bool $ not $ null $ editionsFor c f),("ownedText",val $ if null (editionsFor c f) then "unknown" else "true"),("watched",Bool $ isWatched c f),("watchedText",val $ if isWatched c f then "true" else "false"),("url",val $ filmUrl f),("thumbnail",thumbnail c f),("reviewed",Bool (count>0)),
  ("reviewedText",val $ if count>0 then "true" else "false"),("reviewClass",val $ if count>0 then "reviewed" else "unreviewed"),
  ("reviewStatus",val $ if count==0 then "no review" else show count++if count==1 then " review" else " reviews"),
  ("directors",values [set [("url",val $ directorUrl p)] p | p <- ls "directors" f]),
  ("tags",values [obj [("name",val $ tagLabels c M.! foldCase (text t)),("url",val $ tagUrl (text t))] | t <- ls "tags" f])] f
  where count=length $ ownReviews c f
tagLabels :: Cinema -> M.Map String String
tagLabels c = M.fromListWith (flip const) [(foldCase $ text t,text t) | f <- films c,t <- ls "tags" f]
viewingSummary :: Cinema -> Value -> Value
viewingSummary c v = set [("film",filmSummary c f),("reviews",values $ map (reviewSummary c) related)] v
  where f=filmFor c (str "film" v)
        related=filter (\r -> (truth (get "letterboxd_url" v) && get "letterboxd_url" r==get "letterboxd_url" v) || get "viewing" r==get "id" v) $ ownReviews c f
watchesFor :: Cinema -> Value -> [Value]
watchesFor c f = map (viewingSummary c) $ sortOn (Down . (\v -> (str "date" v,str "id" v))) $ filter ((==str "id" f) . str "film") $ viewings c
filmView :: Cinema -> Value -> Value
filmView c f = set [("filmTheme",get "theme" f),("image",hero c f),("reviews",values $ map (reviewSummary c) $ ownReviews c f),
  ("physicalMedia",values $ map (editionView c) $ editionsFor c f),("viewings",values $ watchesFor c f),("originalTitle",if get "original_title" f/=get "title" f then get "original_title" f else Null),
  ("tmdbUrl",if truth t then val ("https://www.themoviedb.org/"++str "type" t++"/"++str "id" t) else Null)] (filmSummary c f)
  where t=get "tmdb" f
reviewView :: Cinema -> Value -> Value
reviewView c r = set [("filmTheme",get "theme" $ filmFor c $ str "film" r),("film",filmSummary c $ filmFor c $ str "film" r),("image",reviewImage r),
  ("otherReviews",values $ map (reviewSummary c) $ filter ((/=str "id" r) . str "id") $ ownReviews c $ filmFor c $ str "film" r)] r

knownPeople :: Cinema -> [Value]
knownPeople c = filter (not.null.owned) $ M.elems $ M.union stored extra
  where stored=M.fromList [(str "id" p,p) | p<-people c]
        extra=M.fromList [(str "id" p,p) | f<-films c,p<-ls "directors" f]
        owned p=[f|f<-films c,any ((==str "id" p).str "id") $ ls "directors" f]
directorView :: Cinema -> Value -> Value
directorView c p = set [("url",val $ directorUrl p),("watchedCount",number $ length $ filter (isWatched c) owned),
  ("reviewedCount",number $ length $ filter (not.null.ownReviews c) owned),("filmography",values sortedEntries)] p
  where owned=[f|f<-films c,any ((==str "id" p).str "id") $ ls "directors" f]
        byTmdb=M.fromList [(str "id" (get "tmdb" f),f)|f<-films c,str "type" (get "tmdb" f)=="movie"]
        credits=ls "filmography" p
        included=S.fromList [str "tmdb_id" x|x<-credits]
        watched f=obj [("title",get "title" f),("year",get "year" f),("film",filmSummary c f),
                       ("status",val $ if not (null $ ownReviews c f) then "reviewed" else if isWatched c f then "watched · no review" else "No viewing recorded"),
                       ("filterStatus",val $ if not (null $ ownReviews c f) then "reviewed" else if isWatched c f then "watched" else "unwatched")]
        credit x=maybe (set [("status",val "not watched"),("filterStatus",val "unwatched")] x) watched (M.lookup (str "tmdb_id" x) byTmdb)
        entries=map credit credits ++ [watched f|f<-owned,not $ S.member (str "id" $ get "tmdb" f) included]
        sortedEntries=sortOn (\x->(if null (str "year" x) then "9999" else str "year" x,str "title" x)) entries


-- Public collection views are allowlisted; never expose copy notes or locations.
isWatched :: Cinema -> Value -> Bool
isWatched c f = get "watched" f == Bool True || any ((==str "id" f).str "film") (viewings c)
ownedCopies :: Cinema -> [Value]
ownedCopies c = filter copyIsOwned $ ls "copies" $ collection c
copyIsOwned :: Value -> Bool
copyIsOwned x = get "ownership" x == Null || str "ownership" x `elem` ["owned","loaned"]
ownedEditions :: Cinema -> [Value]
ownedEditions = ownedReleaseRows
editionUrl :: Value -> String
editionUrl e = "/films/collection/editions/" ++ str "id" e ++ "/"
workUrl :: Value -> String
workUrl w = "/films/collection/works/" ++ str "id" w ++ "/"
editionsFor :: Cinema -> Value -> [Value]
editionsFor c f = M.findWithDefault [] (str "id" f) $ releaseLinks c
editionView :: Cinema -> Value -> Value
editionView c e = obj [("editionTitle",get "title" e),("url",val $ editionUrl e),
  ("label",maybe Null (get "name") $ M.lookup (str "label_id" e) labels),("formats",val $ intercalate ", " $ map text $ ls "formats" e),
  ("imprint",get "imprint" e),("catalogueNumber",get "catalogue_number" e),("barcode",get "barcode" e),
  ("country",get "country" e),("releaseDate",get "release_date" e),("packaging",get "packaging" e),
  ("copyCount",number $ length [x|x<-ownedCopies c,str "edition_id" x==str "id" e]),
  ("contents",values $ map content $ ls "contents" e)]
  where catalogue=M.fromList [(str "id" f,f)|f<-films c]
        labels=M.fromList [(str "id" l,l)|l<-ls "labels" $ collection c]
        content entry = let f=catalogue M.! str "film" entry
                        in obj [("title",get "title" f),("year",get "year" f),("url",val $ filmUrl f),
                                ("linked",Bool True),("kind",get "kind" f),("cut",get "cut" entry),("coverage",get "coverage" entry)]

-- Route declarations and their template data, all derived from source records.
pageViews :: Cinema -> [(String,FilePath,Value)]
pageViews c = fixed ++ filmPages ++ directorPages ++ tagPages ++ editionPages ++ collectionWorkPages
  where latest=latestReviews c
        summary=map (reviewSummary c)
        sortedFilms=sortOn (\f->(foldCase $ str "title" f,str "year" f))
        catalogue=obj [("films",values $ map (filmSummary c) $ sortedFilms $ films c),("recent",values $ summary $ take 3 latest),
                       ("filmCount",number $ length $ films c),("viewingCount",number $ length $ viewings c),("reviewCount",number $ length latest)]
        sortedWatches=sortOn (Down . (\v->(str "date" v,str "id" v))) $ viewings c
        years=groupBy (\a b->take 4 (str "date" a)==take 4 (str "date" b)) sortedWatches
        diary=obj [("years",values [obj [("year",val $ take 4 $ str "date" y),("viewings",values $ map (viewingSummary c) ys)]|ys@(y:_)<-years])]
        ps=sortOn (foldCase.str "name") $ knownPeople c
        initials=map (map toUpperAscii . take 1 . slug . str "name") ps
        toUpperAscii x=if x>='a' && x<='z' then toEnum (fromEnum x-32) else x
        firsts=M.fromListWith min [(letter,n)|(n,letter)<-zip [0::Int ..] initials]
        directorIndex=obj [("letters",values [obj [("letter",val l)]|l<-M.keys firsts]),
          ("directors",values [set [("initial",if firsts M.! letter==n then val letter else Null)] (directorView c p)|(n,(letter,p))<-zip [0::Int ..] $ zip initials ps])]
        labels=tagLabels c
        tagged key=[f|f<-films c,any ((==key).foldCase.text) $ ls "tags" f]
        tags=[obj [("name",val label),("url",val $ tagUrl label),("count",number $ length $ tagged key),("plural",Bool $ length (tagged key)/=1)]|(key,label)<-M.toList labels]
        page url tpl title v=(url,tpl,set [("title",val title),("nav_"++section url,Bool True)] v)
        section url | "/films/collection/" `isPrefixOf` url="collection" | "/films/tags/" `isPrefixOf` url="tags" | "/directors/" `isPrefixOf` url="directors" | url=="/films/diary/"="diary" | url=="/films/reviews/"="writing" | otherwise="films"
        fixed=[page "/films/collection/" "collection" "Physical collection" $ obj [("editions",values $ map (editionView c) $ sortOn (foldCase . str "title") $ ownedEditions c),("packageCount",number $ length $ ownedCopies c)],
               page "/films/" "catalogue" "Films" catalogue,
               page "/films/diary/" "diary" "Film diary" diary,
               page "/films/reviews/" "writing" "Film reviews" $ obj [("reviews",values $ summary latest)],
               page "/directors/" "directors" "Directors" directorIndex,
               page "/films/tags/" "tags" "Film tags" $ obj [("tags",values tags)]]
        filmPages=[page (filmUrl f) "film" (str "title" f++if truth (get "year" f) then " ("++str "year" f++")" else "") $ set [("filmTitle",get "title" f)] $ filmView c f|f<-films c]
        editionPages=[page (editionUrl e) "edition" (str "title" e) (editionView c e)|e<-ownedEditions c]
        collectionWorkPages=[page ("/films/collection/works/"++old++"/") "collection-work" (str "title" f) $ obj [("workTitle",get "title" f),("year",get "year" f),("canonicalUrl",val $ filmUrl f),("physicalMedia",values $ map (editionView c) $ editionsFor c f)]|(old,fid)<-M.toList $ legacyWorkLinks c,let f=filmFor c fid]
        directorPages=[page (directorUrl p) "director" (str "name" p) (directorView c p)|p<-ps]
        tagPages=[page (tagUrl label) "tag" ("Films tagged "++label) $ obj [("name",val label),("count",number $ length $ tagged key),("plural",Bool $ length (tagged key)/=1),("films",values $ map (filmSummary c) $ sortedFilms $ tagged key)]|(key,label)<-M.toList labels]

featuredReviewView :: Cinema -> Value
featuredReviewView c = obj [("reviews",values $ map (reviewSummary c) chosen),("heading",val heading),
                  ("featuredPool",values $ map (reviewSummary c) $ if length featured > 3 then featured else [])]
  where latest=latestReviews c; featured=filter (truth.get "featured") latest
        chosen=take 3 (featured++filter (not.truth.get "featured") latest)
        heading=if null featured then "Recent film writing" else if length featured>=3 then "Featured reviews" else "Featured and recent reviews"
