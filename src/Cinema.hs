{-# LANGUAGE OverloadedStrings #-}
-- Cinema records and template contexts. Presentation belongs in templates/.
module Cinema where

import Control.Monad (forM, unless, when)
import Crypto.Hash (Digest, SHA256, hash)
import Data.Aeson (Value(..), eitherDecodeStrict', toJSON)
import qualified Data.Aeson.Key as K
import qualified Data.Aeson.KeyMap as KM
import qualified Data.ByteString as BS
import Data.Char (isAscii, isAlphaNum)
import Data.List (sortOn, groupBy, intercalate, isPrefixOf)
import qualified Data.Map.Strict as M
import Data.Maybe (fromMaybe)
import Data.Scientific (formatScientific, FPFormat(Fixed))
import Data.Ord (Down(..))
import qualified Data.Set as S
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Data.Text.Normalize (normalize, NormalizationMode(..))
import Data.Time (Day, defaultTimeLocale, parseTimeM)
import Hakyll
import System.Directory (listDirectory, doesFileExist)
import System.FilePath ((</>), takeExtension, splitDirectories)
import qualified Data.Yaml as Y

get :: String -> Value -> Value
get key (Object o) = fromMaybe Null (KM.lookup (K.fromString key) o)
get _ _ = Null
text :: Value -> String
text (String s) = T.unpack s
text (Number n)
  | fromInteger (round n) == n = show (round n :: Integer)
  | otherwise = formatScientific Fixed Nothing n
text _ = ""
val :: String -> Value
val = String . T.pack
str :: String -> Value -> String
str key = text . get key
arr :: Value -> [Value]
arr (Array a) = foldr (:) [] a
arr _ = []
ls :: String -> Value -> [Value]
ls key = arr . get key
truth :: Value -> Bool
truth Null = False
truth (Bool b) = b
truth (String s) = not (T.null s)
truth (Array a) = not (null a)
truth (Object a) = not (KM.null a)
truth _ = True
set :: [(String, Value)] -> Value -> Value
set fields v = Object $ foldr (uncurry (KM.insert . K.fromString)) original fields
  where original = case v of Object o -> o; _ -> KM.empty
obj :: [(String, Value)] -> Value
obj fields = set fields Null
values :: [Value] -> Value
values = toJSON
number :: Int -> Value
number = val . show
foldCase :: String -> String
foldCase = T.unpack . T.toCaseFold . T.pack
slug :: String -> String
slug = intercalate "-" . filter (not . null) . words . map replace . T.unpack . T.toLower . T.filter isAscii . normalize NFKD . T.pack
  where replace c = if isAlphaNum c then c else ' '
normalTags :: Value -> Either String [String]
normalTags Null = Right []
normalTags (Array a) = do
  labels <- mapM clean (foldr (:) [] a)
  pure $ M.elems $ M.fromListWith (flip const) [(foldCase s,s) | s <- labels]
  where clean (String s) | not (T.null $ T.strip s) = Right $ T.unpack $ normalize NFC $ T.unwords $ T.words s
        clean _ = Left "Tags must be non-empty strings"
normalTags _ = Left "Tags must be a list"
tagUrl :: String -> String
tagUrl label = "/films/tags/" ++ prefix ++ "-" ++ take 12 digest ++ "/"
  where key = foldCase label
        prefix = case take 60 (slug key) of "" -> "tag"; s -> s
        digest = show (hash (TE.encodeUtf8 $ T.pack key) :: Digest SHA256)
filmUrl :: Value -> String
filmUrl f = "/films/" ++ str "slug" f ++ "/"
directorUrl :: Value -> String
directorUrl p = "/directors/" ++ slug (str "name" p) ++ "-" ++ str "id" p ++ "/"
routePath :: String -> FilePath
routePath url = dropWhile (=='/') url ++ "index.html"

-- Retain every review's path, including drafts, so validation runs before routing.
data Cinema = Cinema { films :: [Value], viewings :: [Value], people :: [Value], reviews :: [Value], artwork :: Value }

readJson :: FilePath -> IO Value
readJson path = BS.readFile path >>= either (fail . ((path ++ ": ") ++)) pure . eitherDecodeStrict'
readReview :: FilePath -> IO Value
readReview path = do
  contents <- T.unpack . TE.decodeUtf8 <$> BS.readFile path
  case lines contents of
    "---":rest -> case break (=="---") rest of
      (header,_:body) -> case Y.decodeEither' (TE.encodeUtf8 $ T.pack $ unlines header) of
        Left e -> fail (path ++ ": " ++ show e)
        Right meta -> pure $ set [("source", val path), ("rawBody", val $ unlines body)] meta
      _ -> fail (path ++ ": missing front matter terminator")
    _ -> fail (path ++ ": missing front matter")

loadCinema :: IO Cinema
loadCinema = do
  fs <- arr <$> readJson "cinema/films.json"
  vs <- arr <$> readJson "cinema/viewings.json"
  ps <- arr <$> readJson "cinema/directors.json"
  names <- sortOn id <$> listDirectory "cinema/reviews"
  rs <- mapM (readReview . ("cinema/reviews" </>)) $ filter ((==".md") . takeExtension) names
  exists <- doesFileExist "cinema/artwork.json"
  artworkData <- if exists then readJson "cinema/artwork.json" else pure Null
  tagged <- forM fs $ \f -> either fail (\ts -> pure $ set [("tags",values $ map val ts)] f) (normalTags $ get "tags" f)
  let c = Cinema tagged vs ps rs artworkData
  validate c
  pure c

validate :: Cinema -> IO ()
validate c = do
  unique "film IDs" (map (str "id") $ films c)
  unique "film slugs" (map (str "slug") $ films c)
  unique "viewing IDs" (map (str "id") $ viewings c)
  unique "review IDs" (map (str "id") $ reviews c)
  let ids = S.fromList $ map (str "id") $ films c
      watches = M.fromList [(str "id" v,str "film" v) | v <- viewings c]
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
  mapM_ (\r -> do
    unless (S.member (str "film" r) ids) $ fail "Review refers to missing film"
    unless (all (\x -> isAscii x && (isAlphaNum x || x=='-')) (str "id" r) && not (null $ str "id" r)) $ fail "Unsafe review ID"
    mapM_ (\key -> unless (get key r `elem` [Null,Bool True,Bool False]) $ fail (key ++ " must be true or false")) ["draft","featured"]
    when (truth $ get "viewing" r) $ unless (M.lookup (str "viewing" r) watches == Just (str "film" r)) $ fail "Review viewing belongs to another film"
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
published r = get "draft" r == Bool False
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

-- JSON-shaped view records let templates consume lists and optional fields without
-- constructing HTML in Haskell. Only Markdown compiler results bypass escaping.
valueContext :: Context Value
valueContext = Context $ \key _ item -> case get key (itemBody item) of
  Null -> noResult $ "No field "++key
  String "" -> noResult $ "Empty field "++key
  Bool False -> noResult $ "False field "++key
  Array xs | null xs -> noResult $ "Empty field "++key
  Array xs -> pure $ ListField valueContext [Item (fromFilePath $ show n) v | (n,v) <- zip [0::Int ..] (foldr (:) [] xs)]
  Object o | KM.null o -> noResult $ "Empty field "++key
  v@(Object _) -> pure $ ListField valueContext [Item (fromFilePath key) v]
  Bool True -> pure EmptyField
  v -> pure $ StringField $ if key `elem` ["intro", "htmlBody"] then text v else escapeHtml (text v)
viewContext :: Value -> Context String
viewContext v = bodyField "body" <> Context (\k args i -> unContext valueContext k args (Item (itemIdentifier i) v))

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
filmSummary c f = set [("url",val $ filmUrl f),("thumbnail",thumbnail c f),("reviewed",Bool (count>0)),
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
  ("viewings",values $ watchesFor c f),("originalTitle",if get "original_title" f/=get "title" f then get "original_title" f else Null),
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
directorView c p = set [("url",val $ directorUrl p),("watchedCount",number $ length owned),
  ("reviewedCount",number $ length $ filter (not.null.ownReviews c) owned),("filmography",values sortedEntries)] p
  where owned=[f|f<-films c,any ((==str "id" p).str "id") $ ls "directors" f]
        byTmdb=M.fromList [(str "id" (get "tmdb" f),f)|f<-films c,str "type" (get "tmdb" f)=="movie"]
        credits=ls "filmography" p
        included=S.fromList [str "tmdb_id" x|x<-credits]
        watched f=obj [("title",get "title" f),("year",get "year" f),("film",filmSummary c f),
                       ("status",val $ if null (ownReviews c f) then "watched · no review" else "reviewed"),
                       ("filterStatus",val $ if null (ownReviews c f) then "watched" else "reviewed")]
        credit x=maybe (set [("status",val "not watched"),("filterStatus",val "unwatched")] x) watched (M.lookup (str "tmdb_id" x) byTmdb)
        entries=map credit credits ++ [watched f|f<-owned,not $ S.member (str "id" $ get "tmdb" f) included]
        sortedEntries=sortOn (\x->(if null (str "year" x) then "9999" else str "year" x,str "title" x)) entries

-- Route declarations and their template data, all derived from source records.
pageViews :: Cinema -> [(String,FilePath,Value)]
pageViews c = fixed ++ filmPages ++ directorPages ++ tagPages
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
        section url | "/films/tags/" `isPrefixOf` url="tags" | "/directors/" `isPrefixOf` url="directors" | url=="/films/diary/"="diary" | url=="/films/reviews/"="writing" | otherwise="films"
        fixed=[page "/films/" "catalogue" "Films" catalogue,
               page "/films/diary/" "diary" "Film diary" diary,
               page "/films/reviews/" "writing" "Film reviews" $ obj [("reviews",values $ summary latest)],
               page "/directors/" "directors" "Directors" directorIndex,
               page "/films/tags/" "tags" "Film tags" $ obj [("tags",values tags)]]
        filmPages=[page (filmUrl f) "film" (str "title" f++" ("++str "year" f++")") $ set [("filmTitle",get "title" f)] $ filmView c f|f<-films c]
        directorPages=[page (directorUrl p) "director" (str "name" p) (directorView c p)|p<-ps]
        tagPages=[page (tagUrl label) "tag" ("Films tagged "++label) $ obj [("name",val label),("count",number $ length $ tagged key),("plural",Bool $ length (tagged key)/=1),("films",values $ map (filmSummary c) $ sortedFilms $ tagged key)]|(key,label)<-M.toList labels]

homeView :: Cinema -> Value
homeView c = obj [("reviews",values $ map (reviewSummary c) chosen),("heading",val heading),
                  ("featuredPool",values $ map (reviewSummary c) $ if length featured > 3 then featured else [])]
  where latest=latestReviews c; featured=filter (truth.get "featured") latest
        chosen=take 3 (featured++filter (not.truth.get "featured") latest)
        heading=if null featured then "Recent film writing" else if length featured>=3 then "Featured reviews" else "Featured and recent reviews"
